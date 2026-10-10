export type Baserevision = number;
/**
 * @maxItems 100
 */
export type Achievements = string[];
export type Name = string;
export type Summary = string;
export type Title = string;
/**
 * @maxItems 8
 */
export type Focus =
  | []
  | [FocusItem]
  | [FocusItem, FocusItem]
  | [FocusItem, FocusItem, FocusItem]
  | [FocusItem, FocusItem, FocusItem, FocusItem]
  | [FocusItem, FocusItem, FocusItem, FocusItem, FocusItem]
  | [FocusItem, FocusItem, FocusItem, FocusItem, FocusItem, FocusItem]
  | [FocusItem, FocusItem, FocusItem, FocusItem, FocusItem, FocusItem, FocusItem]
  | [FocusItem, FocusItem, FocusItem, FocusItem, FocusItem, FocusItem, FocusItem, FocusItem];
export type Duration = string;
export type Icon = string;
export type Label = string;
export type Footer = string;
export type Company = string;
export type Description = string;
export type Period = string;
/**
 * @maxItems 100
 */
export type Results = string[];
export type Role = string;
export type Stack = string;
/**
 * @maxItems 100
 */
export type Tasks = string[];
/**
 * @maxItems 60
 */
export type Projects = Project[];
/**
 * @maxItems 100
 */
export type Items = string[];
export type Title1 = string;
/**
 * @maxItems 40
 */
export type Sidebar = SidebarSection[];
export type Items1 = string;
export type Title2 = string;
/**
 * @maxItems 40
 */
export type Skillgroups = SkillGroup[];
export type Id = string;
export type Projectrevision = number;
export type Renderersha256 = string;
export type Rendererversion = "1.0.0";
export type Snapshotsha256 = string;
export type Templateid = "generic";
export type Templatepackagesha256 = string;
export type Templateversion = "1.0.0";

export interface RenderRequest {
  baseRevision: Baserevision;
  document: RenderDocument;
  snapshot: RenderIdentity;
}
export interface RenderDocument {
  achievements: Achievements;
  candidate: Candidate;
  focus: Focus;
  footer: Footer;
  projects: Projects;
  sidebar: Sidebar;
  skillGroups: Skillgroups;
}
export interface Candidate {
  name: Name;
  summary: Summary;
  title: Title;
}
export interface FocusItem {
  duration: Duration;
  icon: Icon;
  label: Label;
}
export interface Project {
  company: Company;
  description: Description;
  period: Period;
  results: Results;
  role: Role;
  stack: Stack;
  tasks: Tasks;
}
export interface SidebarSection {
  items: Items;
  title: Title1;
}
export interface SkillGroup {
  items: Items1;
  title: Title2;
}
export interface RenderIdentity {
  id: Id;
  projectRevision: Projectrevision;
  rendererSha256: Renderersha256;
  rendererVersion: Rendererversion;
  snapshotSha256: Snapshotsha256;
  templateId: Templateid;
  templatePackageSha256: Templatepackagesha256;
  templateVersion: Templateversion;
}
