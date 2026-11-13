"""Register the decoders this package needs before anything opens a file.

A phone hands over HEIC and AVIF, so those have to be readable or the inbox silently
ignores half of her camera roll. pillow-heif is a free local wheel - no service, no key.
"""

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # without the wheel the rest still reads jpg/png/webp/tiff
    pass
