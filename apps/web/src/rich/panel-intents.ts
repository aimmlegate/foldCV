export const technologyName = (value: string): string => value.trim().replace(/\s+/gu, " ");
export const technologyKey = (value: string): string => technologyName(value).toLocaleLowerCase();
