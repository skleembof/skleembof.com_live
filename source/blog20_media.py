#!/usr/bin/env python
#miscellaneous media tools

from waflib import Task, TaskGen, Errors

IMAGE_FORMATS = [
	'.png','.bmp','.webp','.jpg','.jfif','.pjpeg','.pjp','.jpeg','.tiff', #'.gif', #breaks animations!
	'.psd', '.dib', '.ico', '.icns', '.j2k', '.pcx', '.xbm', '.tga', '.eps', '.apng',
	'.msp', '.ppm', '.sgi', '.spi', '.fpx', '.gbr', '.wmf'
]

def options(opt):
	opt.add_option('--no-gif-optimizer', dest='nogifopt', action="store_true", default=False, help="Disable all gif optimizations (improves build time)")
	opt.add_option('--no-img-convert', dest='noimgconv', action="store_true", default=False, help="Disable all image conversion (improves build time)")
	opt.add_option('--img-shrink-maximum', dest='img_shrink_maxsize', type='int', default=512, help='Maximum allowed size in any dimension for images during shrinking (default: 512)')
	opt.add_option('--img-convert-format', dest='img_convert_fmt', type='string', default="webp", help='output format during image conversions (default: "webp")')
	opt.add_option('--snd-convert-format', dest='snd_convert_fmt', type='string', default="webp", help='output format during audio conversions (default: "mp3")')

def configure(conf):
	#defaults
	if conf.env.MAX_IMG_DIMENSION == []:
		conf.env.MAX_IMG_DIMENSION = conf.options.img_shrink_maxsize

	if conf.env.IMAGE_FMT_OUT == []:
		conf.env.IMAGE_FMT_OUT = conf.options.img_convert_fmt
		
	if conf.env.SOUND_FMT_OUT == []:
		conf.env.SOUND_FMT_OUT = conf.options.snd_convert_fmt

	conf.env.img_replacement_map = {}

	conf.env.HAS_BLOG20_MEDIA = True
	conf.env.DISABLE_GIF_OPTIMIZATION = conf.options.nogifopt
	conf.env.DISABLE_IMG_CONVERSION = conf.options.noimgconv

	#find required modules
	failed = False
	"""
	try:
		conf.start_msg("Checking for pydub")
		import pydub
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True
	try:
		conf.start_msg("Checking for pyttsx3")
		import pyttsx3
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True
	"""
	try:
		conf.start_msg("Checking for Pillow")
		import PIL
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True
	
	try:
		conf.start_msg("Checking for pygifsicle")
		conf.find_program("gifsicle")
		import pygifsicle
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True

	if failed:
		raise Errors.ConfigurationError('Missing required Python modules')


@TaskGen.feature("copyfiles")
@TaskGen.before_method("proc_index")
@TaskGen.before_method("proc_copyfiles")
@TaskGen.before_method("process_source")
def process_convert_image(self):
	if getattr(self, 'convert_images', False) == False:
		return
	files = self.to_nodes(getattr(self, 'copyfiles', []))

	#self.img_replacement_map = {}
	for i in range(0,len(files)):
		file = files[i]
		if file.suffix() in IMAGE_FORMATS and self.env.DISABLE_IMG_CONVERSION != True:
			outnode = file.change_ext('.%s' % self.env.IMAGE_FMT_OUT)
			tsk = self.create_task('ConvertImage', [file], [outnode])
			if getattr(file, 'dont_shrink', False) == True:
				tsk.do_shrink = False
			else:
				tsk.do_shrink = getattr(self, 'shrink_images', True)
			files[i] = outnode
			self.env.img_replacement_map[file.abspath()] = outnode.abspath()
		elif file.suffix() == ".gif" and self.env.DISABLE_GIF_OPTIMIZATION != True: #use gifsicle!
			outnode = file.get_bld().change_ext(".optimized.gif")
			files[i] = outnode
			self.env.img_replacement_map[file.abspath()] = outnode.abspath()
			tsk = self.create_task('OptimizeGif', [file], [outnode])
			tsk.gif_options = getattr(self, "gif_options", None)

	self.copyfiles = files

class OptimizeGif(Task.Task):
	before = ['BuildMdContent']

	def run(self):
			from pygifsicle import gifsicle

			gif_optimize = True
			gif_colors = None
			gifsicle_opts = None

			if getattr(self, "gif_options", None) != None:
				gif_optimize = self.gif_options.get('optimize', True)
				gif_colors = self.gif_options.get('colors', None)
				gifsicle_opts = self.gif_options.get('gifsicle_options', ['--verbose'])

			gifsicle(
				sources=self.inputs[0].abspath(),
				destination=self.outputs[0].abspath(),
				optimize=gif_optimize,
				colors=gif_colors,
				options=gifsicle_opts
			)		


class ConvertImage(Task.Task):
	before = ['BuildMdContent', 'GeneratePageTemplate', 'GenerateIndex']
	#converts input images to PNG format
	def run(self):
		from PIL import Image
		for node in self.inputs:
			img = Image.open(node.abspath())
			
			if self.do_shrink:
				if getattr(node, 'make_square', False):
					#make square
					img = img.convert('RGBA')
					background = Image.new('RGBA', img.size, (255,255,255))
					img = Image.alpha_composite(background, img)
					min_dim = min(img.size[0], img.size[1])
					img = self.make_square(img, min_dim, (255, 255, 255, 0));
					img = img.convert('RGB')

				max_dim = getattr(node, 'max_dimension', self.env.MAX_IMG_DIMENSION)

				if max(img.size[0], img.size[1]) > max_dim:
					ratio = float(img.size[0]) / float(img.size[1])
					if ratio > 1:
						img = img.resize((max_dim, int(max_dim * (1.0 / ratio))))
					else:
						img = img.resize((int(max_dim * ratio), max_dim))


			img.save(self.outputs[0].abspath(), format = self.env.IMAGE_FMT_OUT, lossless = True)
	
	def make_square(self, im, min_size, fill_color):
		from PIL import Image
		x, y = im.size
		size = max(min_size, x, y)
		new_im = Image.new('RGBA', (size, size), fill_color)
		new_im.paste(im, (int((size - x) / 2), int((size - y) / 2)))
		return new_im
"""
class GenerateTTS(Task.Task):
	def run(self):
		for i in range(0, len(self.inputs)):
			msg = self.inputs[i].name
			outnode = self.outputs[i]
			with tts_lock: #gross
				self.engine.save_to_file(msg, outnode.abspath())
				self.engine.runAndWait()

class ConvertSound(Task.Task):
	def run(self):
		from pydub import AudioSegment
		for node in self.inputs:
			segment = AudioSegment.from_file(node.abspath())
			segment.export(self.outputs[0].abspath(), self.env.SOUND_FMT_OUT)
"""