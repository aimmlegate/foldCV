"""Where a résumé's photo stands (D187): the place a template declares in `style.header.photo`, else a default place
for a template made before D187, so an older résumé can get a photo too without a new package (G2-d)."""

from ..models.template_package import PhotoPlace

# The default fits the space between the name's top and the divider, within these bounds, as a square with corners of
# 12 % of its side.
SMALLEST, LARGEST, GAP, RADIUS = 40.0, 72.0, 12.0, 0.12


def photo_place(recipe):
    """The template's photo place, or the default one: at the header region's left edge and the name's top, as large as
    the header allows (the header grows when even the smallest size does not fit)."""
    header = recipe.style.header
    if header.photo is not None:
        return header.photo
    region = recipe.layout.regions[0]
    bottom = header.divider.y if header.divider is not None else recipe.style.page.first_body_top
    size = max(SMALLEST, min(LARGEST, bottom - header.name_top - 4))
    return PhotoPlace(x=region.x, top=header.name_top, size=round(size, 2), radius=round(size * RADIUS, 2), gap=GAP)


def photo_growth(recipe):
    """How far the photo reaches below the header's own space; 0 when it fits."""
    place, header = photo_place(recipe), recipe.style.header
    bottom = header.divider.y if header.divider is not None else recipe.style.page.first_body_top
    return max(0.0, place.top + place.size - bottom)
