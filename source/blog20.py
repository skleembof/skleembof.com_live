#!/usr/bin/env python
import json, datetime
from waflib import Task, TaskGen, Errors
from waflib.Errors import WafError
import xml.dom.minidom as minidom
from string import Template
import re

MDExtensions = [
	'markdown.extensions.codehilite',
	'markdown.extensions.fenced_code',
	'markdown.extensions.tables'
]

MDExtensions_Config = {
	'markdown.extensions.codehilite': {
		'linenums': True,
		'guess_lang': False,
	}
}

def configure(conf):
	#find required modules
	failed = False

	try:
		conf.start_msg("Checking for pygments")
		import pygments
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True

	try:
		conf.start_msg("Checking for markdown")
		import markdown
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True

	try:
		conf.start_msg("Checking for rfeed")
		import rfeed
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True

	try:
		conf.start_msg("Checking for GitPython")
		import git
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True

	try:
		conf.start_msg("Checking for pyyaml")
		import yaml
		conf.end_msg("OK")
	except ImportError as e:
		conf.end_msg(e, color = 'RED')
		failed = True

	if failed:
		install_command = "python3 -m pip install pygments markdown rfeed GitPython pyyaml"
		raise Errors.ConfigurationError('Missing required Python modules. Install them with:\n\t\"%s\"' % install_command)

def parse_datestr(instr):
	if '/' in instr:
		sp = instr.split('/')
		dstr = sp[0]
		tsp = sp[1].split(':')
		while len(tsp) < 3:
			tsp.append('0')
		time = (int(tsp[0]), int(tsp[1]), int(tsp[2]))
	else:
		dstr = instr
		time = None
	dsp = dstr.split('-')
	date = (int(dsp[0]), int(dsp[1]), int(dsp[2]))

	if time != None:
		return datetime.datetime(date[0], date[1], date[2], time[0], time[1], time[2])
	else:
		return datetime.datetime(date[0], date[1], date[2])

@TaskGen.taskgen_method
def get_static_dir_root(self):
	return self.bld.bldnode.find_or_declare('static')

@TaskGen.taskgen_method
def get_static_dir(self):
	self.static_dir = getattr(self, 'static_dir', self.bld.bldnode.find_or_declare('static'))
	if getattr(self, 'static_root', None) != None:
		if self.static_dir.name != self.static_root:
			self.static_dir = self.static_dir.find_or_declare(self.static_root)
	return self.static_dir

@TaskGen.feature("index")
@TaskGen.after_method("process_source", "proc_series")
def proc_index(self):
	self.get_static_dir()
	tpl = self.to_nodes(self.to_list(getattr(self, 'template', self.bld.root.find_node(self.env['tpl_main']))))[0]
	navmenu = getattr(self, 'navmenu', self.env.NavMenu)
	self.index_page = self.static_dir.find_or_declare(self.target).find_or_declare("index.html")
	tmpdir = self.path.find_or_declare("tmp/index")
	tmpdir.mkdir()
	tmpnode = tmpdir.find_or_declare(self.target + '.html')
	tsk = self.create_task('GenerateIndex', self.source, [tmpnode])
	tsk.node_deps = [tpl]
	tsk.index_root_src = self.path
	tsk.template = tpl
	tsk.navmenu = navmenu

	uselist = self.to_list(getattr(self, 'use', []))
	for usename in uselist:
		try:
			tg = self.bld.get_tgen_by_name(usename)
			tg.post()
			[tsk.set_run_after(t) for t in tg.tasks]
		except WafError:
			continue

	if getattr(self, 'custom_index', None) != None:
		mdIdx = self.path.find_node(self.custom_index)
		self.custom_index_html = mdIdx.change_ext(".custom_index.html")
		self.custom_index_mdt = self.create_task('BuildMdContent', [mdIdx], [self.custom_index_html])
		tsk.inputs.append(mdIdx)

	self.create_task('CopyFiles', tsk.outputs, [self.index_page])

@TaskGen.feature("copyfiles")
def proc_copyfiles(self):
	self.copyfiles = self.to_nodes(getattr(self, 'copyfiles', []))
	self.static_dir = self.get_static_dir()
	for file in self.copyfiles:
		outnode = self.static_dir.find_or_declare(self.target).find_or_declare(file.get_src().path_from(self.path))
		self.create_task('CopyFiles', [file], [outnode])

@TaskGen.feature("page_template")
@TaskGen.after_method("process_source")
@TaskGen.after_method("proc_index")
def proc_ptemplate(self):
	tpl = self.to_nodes(self.to_list(getattr(self, 'template', self.bld.root.find_node(self.env['tpl_main']))))[0]
	navmenu = getattr(self, 'navmenu', self.env.NavMenu)
	self.mdout = getattr(self, 'mdout', [])
	for md in self.mdout:
		if getattr(self, 'index_page', None) == None:
			self.index_page = self.get_static_dir().find_or_declare(self.target).find_or_declare('index.html')
			outnode = self.index_page
		else:
			outnode = self.get_static_dir().find_or_declare(self.target).find_or_declare(md.outputs[0].name)
		tsk = self.create_task('GeneratePageTemplate', [md.outputs[0]], [md.outputs[0].change_ext('_compiled.html')])
		tsk.mdt = md
		tsk.template = tpl
		tsk.navmenu = navmenu

		if getattr(self, "series_meta", None) != None:
			meta = self.series_meta[md.inputs[0].abspath()]
			meta_prev = meta["prev"]
			meta_next = meta["next"]

			if meta_prev != None:
				n_prev = [m for m in self.mdout if m.inputs[0] == meta_prev][0]
			else:
				n_prev = None

			if meta_next != None:
				n_next = [m for m in self.mdout if m.inputs[0] == meta_next][0]
			else:
				n_next = None

			tsk.series = [n_prev, n_next]

		self.create_task('CopyFiles', [tsk.outputs[0]], [outnode])

@TaskGen.feature("series")
@TaskGen.before_method("process_source")
@TaskGen.before_method("proc_index")
def proc_series(self):
	pages = self.to_list(getattr(self, 'pages', []))

	indent_level = 0
	self.series_meta = {
		'@meta': {
			'target': self.target,
			#...
		}
	}
	last = None
	for page in pages:
		sp = page.split('\t')
		if len(sp) - 1 > indent_level:
			indent_level += 1
		elif len(sp) - 1 < indent_level:
			indent_level = len(sp) - 1

		node = self.to_nodes(sp[len(sp)-1])[0]
		self.source.append(node)

		self.series_meta[node.abspath()] = {
			'indent': indent_level,
			'prev': last,
			'next': None
		}

		if last != None:
			self.series_meta[last.abspath()]['next'] = node
		last = node

@TaskGen.feature("pygmentize")
def proc_pygmentize(self):
	outnode = self.path.find_or_declare(self.target).find_or_declare("syntax-style.css")
	self.create_task('Pygmentize', [], [outnode])
	self.create_task('CopyFiles', [outnode], [self.get_static_dir()])

@TaskGen.extension(".md", ".md_mv")
def proc_markdown(self, node):
	outnode = self.path.find_or_declare(self.target).find_or_declare(node.change_ext(".html").name)
	tsk = self.create_task('BuildMdContent', [node], [outnode])
	self.mdout = getattr(self, 'mdout', [])
	self.mdout.append(tsk)

@TaskGen.feature("modelviewer")
@TaskGen.before("process_source")
def proc_modelviewer(self):
	srcnodes = self.to_nodes(getattr(self, 'source', []))
	new_sources = []
	for i in range(0, len(srcnodes)):
		node = srcnodes[i]
		if node.name.endswith(".md"):
			outnode = node.change_ext(".md_mv")
			mvtsk = self.create_task('ModelViewerPreproc', [node], [outnode])
			new_sources.append(outnode)
		else:
			new_sources.append(node)
	self.source = new_sources

@TaskGen.feature("rss_channel")
def tg_make_rss_feed(self):
	"""
		Generate an RSS feed using rfeed
	"""
	items = self.to_nodes(getattr(self, 'rss_items', self.source))
	channel_info = getattr(self, "rss_channel_info", {})
	outnode = getattr(self, 'rss_channel_target', self.get_static_dir().find_or_declare(self.target).find_or_declare("rss.xml"))
	t = self.create_task('GenerateRSSChannel', items, [outnode])
	t.channel_info = channel_info

def extract_meta_header(mdnode):
	"""
		Extracts metadata header from a markdown file.
		Returns a tuple where:
			* the first element is the parsed metadata json object
			* the second element is the md file's content without the metadata header
	"""
	src = mdnode.read(encoding='utf-8')
	meta = None
	sp = src.split('-----')
	if len(sp) > 1:
		metajson = sp[0]
		meta = json.loads(metajson)
		md = '-----'.join(sp[1:])
	else:
		md = sp[0]
	return (meta, md)

class CopyFiles(Task.Task):
	def run(self):
		def dummy(n): return n
		procfunc = {
			".png": dummy, ".jpg": dummy, ".jpeg": dummy
		}
		suffix = self.inputs[0].suffix()
		if suffix in procfunc:
			procdir = self.generator.path.find_or_declare("processed")
			procdir.mkdir()
			processed = procfunc[suffix](self.inputs[0].read())
			outnode = procdir.find_or_declare(self.inputs[0].name)
			outnode.write(processed)
			self.inputs = [outnode]
		self.exec_command(['cp', '-r', self.inputs[0].abspath(), self.outputs[0].abspath()])

class Pygmentize(Task.Task):
	#always_run = True

	def scan(self):
		return ([], self.generator.syntax_themes)

	def runnable_status(self):
		ret = super().runnable_status()
		#rebuild if syntax themes changed
		if self.generator.bld.raw_deps[self.uid()] != self.generator.syntax_themes:
			self.generator.bld.raw_deps[self.uid()] = self.generator.syntax_themes
			return Task.RUN_ME
		return ret

	def run(self):
		import pygments, pygments.formatters.html
		styles = getattr(self.generator,'syntax_themes', {"light":"default","dark":"default"})
		schemes = styles.keys()
		out_css = ""
		for scheme in schemes:
			css = pygments.formatters.HtmlFormatter(style = styles[scheme]).get_style_defs(['.codehilite','.codehilitetable'])
			out_css += "@media(prefers-color-scheme: %s){\n%s\n}\n" % (scheme, css)
		self.outputs[0].parent.mkdir()
		self.outputs[0].write(out_css)

class BuildMdContent(Task.Task):
	"""
		This will compile a markdown content document
	"""
	def run(self):
		self.meta = {}

		import markdown
		from markdown import markdown
		self.outputs[0].parent.mkdir()
		
		(self.meta, md) = extract_meta_header(self.inputs[0])

		if getattr(self.env, 'img_replacement_map', None) != None:
			md = self.update_images(md, self.env.img_replacement_map)

		header = ""
		footer = ""

		if "title" in self.meta:
			header += '# %s\n' % self.meta['title']

		if "date" in self.meta:
			header += '<p class="article-date">%s</p>\n' % parse_datestr(self.meta["date"]).strftime(self.env.DATE_FORMAT_STRING)

		html = '<span>%s</span>' % (
			markdown(
				text = '%s\n%s\n%s' % (header, md, footer),
				output = self.outputs[0].abspath(),
				extensions = MDExtensions,
				extensions_config = MDExtensions_Config
			)
		)

		self.outputs[0].write(html, encoding = "utf-8")

	def runnable_status(self):
		ret = super().runnable_status()
		if ret == Task.SKIP_ME:
			(self.meta, _) = extract_meta_header(self.inputs[0])
		return ret

	def update_images(self, src, replacements):
		for original in replacements.keys():
			new = replacements[original]

			original_node = self.generator.bld.root.find_node(original)
			new_node = self.generator.bld.root.find_node(new)

			original_rel = original_node.path_from(self.generator.path).replace('\\', '/')
			new_rel = new_node.get_src().path_from(self.generator.path).replace('\\', '/')

			src = re.sub(
				"!\\[(.*)\\]\\(%s\\)" % original_rel,
				"![\\1](%s)" % new_rel,
				src
			)

			src = re.sub(
				"src[ ?]*=[ ?]*\"%s\"" % original_rel,
				"src=\"%s\"" % new_rel,
				src
			)
		return src

def format_title(title, limit = 0):
	ret = title.replace('-', ' ').replace('\\ ', '-')
	if limit > 0 and len(ret) > limit:
		ret = (ret[:limit] + '…')
	return ret

def genGetIdDict(dom):
	divs = dom.getElementsByTagName("div") + dom.getElementsByTagName("article") + dom.getElementsByTagName("ul")
	elms = {}
	for e in divs:
		elms[e.getAttribute("id")] = e
	return elms

def genCopyright(gen, dom, elm):
	year = datetime.date.today().year
	copyright = dom.createElement('p')
	copyright.setAttribute('class', 'copyright')
	copyright.appendChild(dom.createTextNode(gen.env.COPYRIGHT_STRING % year))
	elm.appendChild(copyright)

def genNavMenu(gen, dom, elmMenu, navmenu):
	for item in navmenu:
		if isinstance(item, tuple):
			href = item[1]
			item = item[0]
		else:	
			try:
				tg = gen.bld.get_tgen_by_name(item)
				href = '/'+item
			except WafError:
				href = '#'
		elm = dom.createElement('li')

		anchor = dom.createElement('a')
		anchor.setAttribute('class', 'menu-item')
		anchor.setAttribute('href', str(href))
		anchor.appendChild(dom.createTextNode(item))
		elm.appendChild(anchor)

		elmMenu.appendChild(elm)

def genOpenGraph(self, dom, mdt, title, urlpath = None):

	if "og:title" in mdt.meta:
		opengraph = [("og:title", mdt.meta['og:title'])]
	else:
		opengraph = [("og:title", title)]

	if "og:description" in mdt.meta: opengraph.append(("og:description", mdt.meta['og:description']))
	elif "description" in mdt.meta: opengraph.append(("og:description", mdt.meta['description']))

	if "og:type" in mdt.meta: opengraph.append(("og:type", mdt.meta['og:type']))
	elif "type" in mdt.meta: opengraph.append(("og:type", mdt.meta['type']))

	if "og:image" in mdt.meta: opengraph.append(("og:image", mdt.meta['og:image']))
	elif "image" in mdt.meta: opengraph.append(("og:image", mdt.meta['image']))

	if "og:locale" in mdt.meta: opengraph.append(("og:locale", mdt.meta['og:locale']))
	elif "locale" in mdt.meta: opengraph.append(("og:locale", mdt.meta['locale']))
	
	if "og:url" in mdt.meta:
		opengraph.append(("og:url", mdt.meta['og:url']))
	elif "url" in mdt.meta:
		opengraph.append(("og:url", mdt.meta['url']))
	elif urlpath != None:
		opengraph.append(("og:url", '%s/%s' % (self.env.CANONICAL_URL, urlpath)))
	else:
		calculated_url = '%s/%s' % (
			self.env.CANONICAL_URL,
			mdt.inputs[0].change_ext('.html').get_src().path_from(self.generator.path)
		)
		opengraph.append(("og:url", calculated_url))

	head = dom.getElementsByTagName('head')
	for og in opengraph:
		tag = dom.createElement('meta')
		tag.setAttribute("property", str(og[0]))
		tag.setAttribute("content", str(og[1]))
		head[0].appendChild(tag)

class GenerateIndex(Task.Task):
	after = ['GeneratePageTemplate', 'BuildMdContent']
	def run(self):
		tplIndex = Template(self.generator.bld.root.find_node(self.env['tpl_index']).read(encoding = "utf-8"))

		if getattr(self.generator, "template_items", None) == None:
			tisrc = ""
			tplIndexItem = Template(self.generator.bld.root.find_node(self.env['tpl_index_item']).read(encoding = "utf-8"))
		else:
			tisrc = self.generator.to_nodes(self.generator.template_items)[0].read(encoding="utf=8")
			tplIndexItem = Template(tisrc)

		tplIndexItemSeries = Template(self.generator.bld.root.find_node(self.env['tpl_index_item_series']).read(encoding = "utf-8"))

		domTpl = minidom.parse(self.template.abspath())
		elms = genGetIdDict(domTpl)
		outlinks = []
		mdout_list = self.generator.mdout

		index_root = self.generator.index_page

		#collect outlinks from `use` attribute
		uselist = self.generator.to_list(getattr(self.generator, 'use', []))
		for usename in uselist:
			try:
				tg = self.generator.bld.get_tgen_by_name(usename)
				if getattr(tg, 'series_meta', None) != None:
					mdout_list.append((tg.series_meta, tg.mdout))
				elif getattr(tg, 'mdout', None) != None:
					mdout_list.extend(tg.mdout)
			except WafError:
				continue

		def buildIndexItem(mdt, update = None, extra_classes = []):
			if getattr(mdt, 'meta', None) == None:
				print(type(mdt))
				raise WafError("MDT has no meta: %s" % mdt.inputs[0])

			subdict = mdt.meta.copy()
			if update != None:
				subdict.update(update)
			subdict['extra'] = ""
			subdict['extra_classes'] = " ".join(extra_classes)
			if 'title' not in subdict:
				subdict['title'] = mdt.inputs[0].change_ext('').name
			subdict['title'] = format_title(subdict['title'])
			if 'date' in subdict:
				date = parse_datestr(subdict['date'])
				subdict['date'] = date.strftime(self.env.DATE_FORMAT_STRING_INDEX_ITEM)
			else:
				date = None
				subdict['date'] = ""
			subdict['href'] = mdt.inputs[0].change_ext('.html').get_src().path_from(self.index_root_src)

			ti_substr = tplIndexItem.substitute(subdict)

			if getattr(self.env, 'img_replacement_map', None) != None:
				ti_substr = BuildMdContent.update_images(self, ti_substr, self.env.img_replacement_map)

			return (ti_substr, date)

		for mdt in mdout_list:
			if isinstance(mdt, tuple):
				#Series index item
				series_meta = mdt[0]
				mdout = mdt[1]

				title_str = format_title(series_meta['@meta']['target'])

				items = []
				latest_date = None
				for m in mdout:
					indent = ['indent-%s' % series_meta[m.inputs[0].abspath()]['indent']]
					item = buildIndexItem(m, None, indent)
					items.append(item[0])

					if latest_date == None or item[1] > latest_date:
						latest_date = item[1]

				#Series index item
				src = tplIndexItemSeries.substitute({
					'title': '%s (%s)' % (title_str, len(mdout)),
					'href': series_meta['@meta']['target'],
					'date': '',
					'series_items': '\n'.join(items)
				})
				outlinks.append((src, latest_date))

			else:
				#Regular index item
				outlinks.append(buildIndexItem(mdt))

		oldest = datetime.datetime(1995, 7, 14)
		def keyfunc(t):
			if t[1] != None:
				return t[1]
			return oldest
		outlinks.sort(key=keyfunc, reverse=True)

		#series includes a custom index
		items_str = '\n'.join([l[0] for l in outlinks])
		if getattr(self.generator, 'custom_index_html', None) != None:
			idxSrc = self.generator.custom_index_html.read(encoding = "utf-8")
			items_str = Template(idxSrc).substitute({
				"items": items_str
			})

			if 'title' in self.generator.custom_index_mdt.meta:
				title_str = format_title(self.generator.custom_index_mdt.meta['title'])
			else:
				title_str = format_title(self.generator.target)
			urlpath = index_root.parent.path_from(self.generator.get_static_dir_root())
			genOpenGraph(self, domTpl, self.generator.custom_index_mdt, title_str, urlpath)

		subdict = {
			'title': format_title(self.generator.target),
			'items': items_str
		}
		domIndex = minidom.parseString(tplIndex.substitute(subdict))
		elms['MainContent'].appendChild(domIndex.firstChild)

		title = domTpl.getElementsByTagName("title")[0]
		title.removeChild(title.firstChild)
		title.appendChild(domTpl.createTextNode(subdict['title']))

		genNavMenu(self.generator, domTpl, elms["NavMenu"], self.navmenu)
		if "CopyrightString" in elms:
			genCopyright(self.generator, domTpl, elms["CopyrightString"])

		xml_out = domTpl.toxml()
		self.outputs[0].write(xml_out, encoding = "utf-8")


class GeneratePageTemplate(Task.Task):
	after = ['BuildMdContent']
	def run(self):
		domTpl = minidom.parse(self.template.abspath())
		domInput = minidom.parse(self.inputs[0].abspath())
		elms = genGetIdDict(domTpl)
		elms["MainContent"].appendChild(domInput.firstChild)

		title = domTpl.getElementsByTagName("title")[0]

		if 'title' in self.mdt.meta:
			title_str = format_title(self.mdt.meta['title'])
		else:
			title_str = ""

		max_title_len = 24	
		def get_title(t):
			if 'title' in t.meta:
				return format_title(t.meta['title'], max_title_len)
			else:
				return t.inputs[0].change_ext('')

		title.removeChild(title.firstChild)
		title.appendChild(domTpl.createTextNode(title_str))

		genNavMenu(self.generator, domTpl, elms["NavMenu"], self.navmenu)
		genOpenGraph(self, domTpl, self.mdt, get_title(self.mdt))

		if getattr(self, 'series', None) != None:

			if self.series[0] != None:
				meta_prev = self.series[0].meta
				href_prev = self.series[0].inputs[0].change_ext('.html').name
				#prev_title = get_title(self.series[0])
				prev_title = "Previous"
			else:
				meta_prev = None
				href_prev = ""
				prev_title = ""

			if self.series[1] != None:
				meta_next = self.series[1].meta
				href_next = self.series[1].inputs[0].change_ext('.html').name
				#next_title = get_title(self.series[1])
				next_title = "Next"
			else:
				meta_next = None
				href_next = ""
				next_title = ""

			series_title = format_title(self.generator.target, max_title_len)

			tplSeriesNav = Template(self.generator.bld.root.find_node(self.env['tpl_series_nav']).read(encoding = "utf-8"))
			dom = minidom.parseString(tplSeriesNav.substitute({
				'href_prev'		: href_prev,
				'title_prev'	: prev_title,
				'href_next'		: href_next,
				'title_next'	: next_title,
				'href_root'		: "index.html",
				'title_root'	: series_title,
			}))
			elms["MainContent"].appendChild(dom.firstChild)
		
		if "CopyrightString" in elms:
			genCopyright(self.generator, domTpl, elms["CopyrightString"])
		xml_out = domTpl.toxml()
		self.outputs[0].write(xml_out, encoding = "utf-8")

class GenerateRSSChannel(Task.Task):
	after = ['BuildMdContent']
	def run(self):
		import rfeed		
		feed_items = []
		for item in self.inputs:
			i = self.build_feed_item(item)
			if i != None:
				feed_items.append(i)

		bloglink = self.channel_info['link']

		if 'image_url' in self.channel_info != None:
			img = rfeed.Image(
				link = link,
				url = bloglink,
				title = 'image_alt' in self.channel_info or '(image title missing)'
			)
		else:
			img = None

		channel = rfeed.Feed(
			title = self.channel_info['title'],
			link = bloglink,
			image = img,
			description = self.channel_info['description'],
			language = getattr(self.channel_info, "language", "en-US"),
			lastBuildDate = datetime.datetime.now(),
			items = feed_items
		)

		self.outputs[0].write(channel.rss())

	def build_feed_item(self, item):
		import rfeed
		(meta, md) = extract_meta_header(item)

		date = parse_datestr(meta["date"])
		rss = getattr(meta, "rss", None)

		def get_prop(p, default = None):
			ret = default
			
			if p in meta:
				ret = meta[p]

			if rss != None:
				if p in rss:
					ret = rss[p]
			else:
				return ret

		title = get_prop('title')
		description = get_prop('description')
		author = get_prop('author', self.env.GLOBAL_AUTHOR)
		link = get_prop('link', '%s/%s/%s' % (
			self.env.CANONICAL_URL,
			self.generator.target,
			item.change_ext('.html').name
		))

		if title == None or description == None or date == None:
			#Skip item
			missing = []
			if title == None: missing.append('title')
			if description == None: missing.append('description')
			if date == None: missing.append('date')
			print('WARNING: skipping RSS item due to missing info(%s): "%s"' % (str(missing), item.abspath()))
			return None

		return rfeed.Item(
			title = title,
			link = link,
			description = description,
			author = author,
			guid = rfeed.Guid(link),
			pubDate = date
		)



class ModelViewerPreproc(Task.Task):
	"""
		Simplifies the process of adding a model to
		markdown by using YAML

		<DDD>
			Attributes as YAML ...
		</DDD>
	"""
	regex = re.compile("<DDD>(.*?)<\\/DDD>", re.IGNORECASE | re.DOTALL)
	base_tpl = Template('\n\n<span class="main"><model-viewer $attributes><div class="progress-bar hide" slot="progress-bar"><div class="update-bar"></div></div></model-viewer></span>\n\n')
	
	mv_defaults = {
		"bounds":"tight",
		"ar": '1',
		"ar-modes": 'webxr scene-viewer quick-look',
		"camera-controls":"1",
		"shadow-intensity":"1",
		"auto-rotate":"1"
	}

	def run(self):
		assert(len(self.inputs) == len(self.outputs))
		for i in range(0, len(self.inputs)):
			md_node = self.inputs[i]
			md_node_out = self.outputs[i]
			self.process_node(md_node, md_node_out)

	def process_node(self, node_in, node_out):
		mdsrc = node_in.read(encoding='utf-8')

		mdsrc_out = mdsrc
		#find <DDD> entries
		it = self.regex.finditer(mdsrc)
		expansions = []
		for match in it:
			if match:
				ex = self.expand(match)
				expansions.append(ex)
				mdsrc_out = re.sub(match.group(0), ex, mdsrc_out)

		node_out.write(mdsrc_out, encoding='utf-8')

	def expand(self, match):
		import yaml
		#expand a <DDD> into the final HTML
		yamlsrc = match.group(1)

		attribs = {}
		
		#default attributes
		attribs.update(self.mv_defaults)
		
		#attributes from yaml
		attribs.update(yaml.safe_load(yamlsrc))

		out_attribs = []
		
		for key in attribs.keys():
			value = str(attribs[key])
			out_attribs.append('%s=\"%s\"'%(key, value))
		
		return self.base_tpl.substitute({
			"attributes": " ".join(out_attribs)
		})

