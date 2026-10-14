import specification from "../../../../templates/foldcv-reference/spec.json";

export const referenceTemplate = specification;
export const referenceVariables = {
  "--cv-page-width": `${specification.page.width}pt`,
  "--cv-sidebar-width": `${specification.regions.sidebar.width}pt`,
  "--cv-main-width": `${specification.regions.main.width}pt`,
  "--cv-column-gap": `${specification.regions.gap}pt`,
  "--cv-body-left": `${specification.regions.sidebar.x}pt`,
  "--cv-body-size": `${specification.typography.body.size}pt`,
  "--cv-line-height": `${specification.typography.body.lineHeight}pt`,
  "--cv-band-color": specification.sectionBand.background,
};
