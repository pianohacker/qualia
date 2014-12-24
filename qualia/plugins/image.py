from PIL import Image

def auto_add_image(f, original_filename):
	try:
		im = Image.open(original_filename)
		f.set_metadata('image-width', im.size[0])
		f.set_metadata('image-height', im.size[1])
	except OSError:
		pass
