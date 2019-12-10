import asyncio
from concurrent.futures.process import ProcessPoolExecutor
from io import BytesIO
from typing import Optional, Sequence, Tuple

from PIL import Image

ImageSize = Tuple[int, int]
ImageBox = Tuple[int, int, int, int]


class InvalidImage(ValueError):
    pass


async def resize_image(
    image_data: bytes, sizes: Sequence[ImageSize], thumb_sizes: Sequence[ImageSize]
) -> Tuple[bytes, bytes]:
    """
    Resize an image to the biggest of the available sizes.
    """
    with ProcessPoolExecutor(max_workers=1) as pool:
        return await asyncio.get_event_loop().run_in_executor(pool, _resize_image, image_data, sizes, thumb_sizes)


def _resize_image(
    image_data: bytes, sizes: Sequence[ImageSize], thumb_sizes: Sequence[ImageSize]
) -> Tuple[bytes, bytes]:
    try:
        img = Image.open(BytesIO(image_data))
    except OSError:
        raise InvalidImage('invalid image')

    img = _do_resize(img, sizes)

    main_stream = BytesIO()
    img.save(main_stream, 'JPEG', optimize=True, quality=95)

    thumb_img = _do_resize(img, thumb_sizes)
    del img
    thumb_stream = BytesIO()
    thumb_img.save(thumb_stream, 'JPEG', optimize=True, quality=95)

    return main_stream.getvalue(), thumb_stream.getvalue()


def _do_resize(img: Image, sizes: Sequence[ImageSize]) -> Image:
    for width, height in sizes:
        if img.width >= width and img.height >= height:
            resize_to, crop_box = _resize_crop_dims(img, width, height)
            if resize_to:
                img = img.resize(resize_to, Image.ANTIALIAS)
                img = img.crop(crop_box)
            break
    else:
        raise InvalidImage('image too small, minimum size {} x {}'.format(*sizes[-1]))

    return img


def _resize_crop_dims(img: Image, req_width: int, req_height: int) -> Tuple[Optional[ImageSize], Optional[ImageBox]]:
    if img.size == (req_width, req_height):
        return None, None
    aspect_ratio = img.width / img.height
    resize_to: ImageSize
    crop_box: ImageBox
    if aspect_ratio > (req_width / req_height):
        # wide image
        resize_to = int(round(req_height * aspect_ratio)), req_height
        extra = int(round((resize_to[0] - req_width) / 2))
        crop_box = extra, 0, extra + req_width, req_height
    else:
        # tall image
        resize_to = req_width, int(round(req_width / aspect_ratio))
        extra = int(round((resize_to[1] - req_height) / 2))
        crop_box = 0, extra, req_width, extra + req_height
    return resize_to, crop_box
