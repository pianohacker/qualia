# Qualia

<pre>
$ qualia add best-wallpaper.jpg
$ ls ~/q
best-wallpaper.jpg
$ qualia tag best-wallpaper.jpg wallpaper clouds
$ qualia tags:wallpaper
best-wallpaper.jpg (tags: <b>wallpaper</b> clouds)
</pre>

## Philosophy

Qualia is intended to support very rich, carefully organized metadata, while being very efficient
and pragmatic about existing filesystem layouts. We want:

* A very efficient UX for adding new files and editing metadata,
* Powerful search, with predictable syntax, and
* Excellent interoperability with existing software

without the fragility of:

* A heavyweight daemon,
* A FUSE filesystem, or
* a cloud service.
