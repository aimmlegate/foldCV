export type Ops = [
  (
    | SetBlockTextOp
    | ReplaceTextOp
    | InsertBlocksOp
    | DeleteBlocksOp
    | MoveBlockOp
    | FormatBlockOp
    | UpdateFactOp
    | CreateFactOp
    | DeleteFactOp
    | HistoryOp
    | ActionOp
  ),
  ...(
    | SetBlockTextOp
    | ReplaceTextOp
    | InsertBlocksOp
    | DeleteBlocksOp
    | MoveBlockOp
    | FormatBlockOp
    | UpdateFactOp
    | CreateFactOp
    | DeleteFactOp
    | HistoryOp
    | ActionOp
  )[]
];
export type Blockid = string;
export type Cellid = string | null;
export type Field = "content" | "caption";
export type Backgroundcolor = string;
export type Bold = boolean;
export type Code = boolean;
export type Italic = boolean;
export type Strike = boolean;
export type Textcolor = string;
export type Underline = boolean;
export type Op = "set_block_text";
export type Text = string;
export type Blockid1 = string;
export type Cellid1 = string | null;
export type Field1 = "content" | "caption";
export type Find = string;
export type Op1 = "replace_text";
export type Replace = string;
export type Afterblockid = string | null;
/**
 * @minItems 1
 * @maxItems 20
 */
export type Blocks =
  | [NewBlock]
  | [NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock, NewBlock]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ]
  | [
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock,
      NewBlock
    ];
export type Kind = "paragraph" | "heading" | "bullet" | "numbered";
export type Level = 1 | 2 | 3;
export type Text1 = string;
export type Op2 = "insert_blocks";
export type Parentid = string | null;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Blockids = [string, ...string[]];
export type Op3 = "delete_blocks";
export type Afterblockid1 = string | null;
export type Blockid2 = string;
export type Op4 = "move_block";
export type Parentid1 = string | null;
export type Alignment = ("left" | "center" | "right" | "justify") | null;
export type Backgroundcolor1 = string | null;
export type Blockid3 = string;
export type Kind1 = ("paragraph" | "heading" | "bullet" | "numbered") | null;
export type Level1 = (1 | 2 | 3) | null;
export type Op5 = "format_block";
export type Textcolor1 = string | null;
export type Field2 = string;
export type Op6 = "update_fact";
export type Recordid = string;
export type Value = string;
export type Jobid = string | null;
export type Kind2 = "candidate" | "employment" | "technology" | "education" | "language" | "claim" | "period";
export type Op7 = "create_fact";
export type Op8 = "delete_fact";
export type Recordid1 = string;
export type Direction = "undo" | "redo";
export type Op9 = "history";
export type Action = "rename" | "formatting_date" | "archive" | "restore" | "delete";
export type Op10 = "action";
export type Targetid = string | null;
export type Value1 = string | null;
export type Summary = string;

export interface ProposeChangesV1 {
  ops: Ops;
  summary: Summary;
}
export interface SetBlockTextOp {
  blockId: Blockid;
  cellId?: Cellid;
  field?: Field;
  marks?: InlineStyles | null;
  op: Op;
  text: Text;
}
export interface InlineStyles {
  backgroundColor?: Backgroundcolor;
  bold?: Bold;
  code?: Code;
  italic?: Italic;
  strike?: Strike;
  textColor?: Textcolor;
  underline?: Underline;
}
export interface ReplaceTextOp {
  blockId: Blockid1;
  cellId?: Cellid1;
  field?: Field1;
  find: Find;
  op: Op1;
  replace: Replace;
}
export interface InsertBlocksOp {
  afterBlockId?: Afterblockid;
  blocks: Blocks;
  op: Op2;
  parentId?: Parentid;
}
export interface NewBlock {
  kind?: Kind;
  level?: Level;
  text: Text1;
}
export interface DeleteBlocksOp {
  blockIds: Blockids;
  op: Op3;
}
export interface MoveBlockOp {
  afterBlockId?: Afterblockid1;
  blockId: Blockid2;
  op: Op4;
  parentId?: Parentid1;
}
export interface FormatBlockOp {
  alignment?: Alignment;
  backgroundColor?: Backgroundcolor1;
  blockId: Blockid3;
  kind?: Kind1;
  level?: Level1;
  op: Op5;
  textColor?: Textcolor1;
}
export interface UpdateFactOp {
  field: Field2;
  op: Op6;
  recordId: Recordid;
  value: Value;
}
export interface CreateFactOp {
  jobId?: Jobid;
  kind: Kind2;
  op: Op7;
  values?: Values;
}
export interface Values {
  [k: string]: string;
}
export interface DeleteFactOp {
  op: Op8;
  recordId: Recordid1;
}
export interface HistoryOp {
  direction: Direction;
  op: Op9;
}
export interface ActionOp {
  action: Action;
  op: Op10;
  targetId?: Targetid;
  value?: Value1;
}
