export type Items =
  | []
  | [AgentMessage]
  | [AgentMessage, AgentMessage]
  | [AgentMessage, AgentMessage, AgentMessage]
  | [AgentMessage, AgentMessage, AgentMessage, AgentMessage]
  | [AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage]
  | [AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage]
  | [AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage]
  | [AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage, AgentMessage]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ]
  | [
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage,
      AgentMessage
    ];
export type AgentMessage = {
  [k: string]: unknown;
} & {
  [k: string]: unknown;
};
export type Nextcursor = string | null;

export interface AgentMessagePage {
  items: Items;
  nextCursor: Nextcursor;
}
