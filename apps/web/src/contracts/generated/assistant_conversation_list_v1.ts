export type Createdat = string;
export type Id = string;
export type Title = string;
export type Updatedat = string;
/**
 * @maxItems 100
 */
export type Items = AssistantConversationV1[];

export interface AssistantConversationListV1 {
  items: Items;
}
export interface AssistantConversationV1 {
  createdAt: Createdat;
  id: Id;
  title: Title;
  updatedAt: Updatedat;
}
