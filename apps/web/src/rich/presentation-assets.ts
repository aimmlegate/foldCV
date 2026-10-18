import brand from "../../../../skills/format-resume/assets/images/foldcv.png?url";

export { brand };
const bundled = import.meta.glob(["../../../../skills/format-resume/assets/{devicon,images}/*.png", "../../../../assets/technology-library/*.png"], { eager: true, query: "?url", import: "default" });
export const presentationLogos: ReadonlyMap<string, string> = new Map(Object.entries(bundled)
  .filter((entry): entry is [string, string] => typeof entry[1] === "string")
  .map(([path, url]) => [path.replace("../../../../", ""), url]));
