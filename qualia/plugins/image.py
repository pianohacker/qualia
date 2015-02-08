from qualia import config

def register(**kwargs):
	config.DB_STATE_BASE['fields']['image.height'] = config.DerivedDictItem(config.FIELD_ITEM_BASE,
		'type', config.FixedItem('number'),
		'aliases', ['height'],
	)
	config.DB_STATE_BASE['fields']['image.width'] = config.DerivedDictItem(config.FIELD_ITEM_BASE,
		'type', config.FixedItem('number'),
		'aliases', ['width'],
	)

def auto_add_image(f, original_filename):
	from PIL import Image

	try:
		im = Image.open(original_filename)
		f.set_metadata('image.width', im.size[0])
		f.set_metadata('image.height', im.size[1])
	except OSError:
		pass
