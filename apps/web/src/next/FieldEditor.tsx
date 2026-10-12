import { BlockNoteSchema } from "@blocknote/core";
import { ru } from "@blocknote/core/locales";
import { createReactBlockSpec, useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import * as Popover from "@radix-ui/react-popover";
import { forwardRef, useImperativeHandle, useMemo, useRef } from "react";
import { createAdapter, type AdapterCallbacks, type FieldProjection } from "./adapter";
import { AnnotationContext, FieldAnnotations, locateAnnotations } from "./Annotations";
import type { Annotation } from "../contracts/generated/workspace_v5";

const createField = createReactBlockSpec({ type: "resumeField", content: "plain",
  propSchema: { fieldId: { default: "" }, slotId: { default: "" }, label: { default: "" } },
}, { meta: { hardBreakShortcut: "enter", code: true }, render: function Field({ block, contentRef, editor }) {
  const returnToEditor = useRef(false);
  return (
  <section className="next-field" data-field-id={block.props.fieldId} data-slot-id={block.props.slotId}>
    <FieldAnnotations fieldId={block.props.fieldId} />
    <div className="next-field-heading" contentEditable={false}>
      <span>{block.props.label}</span>
      {block.props.fieldId.includes("Text") && block.props.fieldId.includes("period:") && <Popover.Root onOpenChange={open => { if (open) returnToEditor.current = false; }}>
        <Popover.Trigger className="next-date-trigger" data-slot-owner={block.props.slotId} aria-label={`Дата: ${block.props.label}`}>Дата</Popover.Trigger>
        <Popover.Portal><Popover.Content className="next-popover" data-slot-owner={block.props.slotId} sideOffset={6}
          onEscapeKeyDown={() => { returnToEditor.current = true; }}
          onCloseAutoFocus={event => { event.preventDefault(); if (returnToEditor.current) editor.focus(); returnToEditor.current = false; }}>
          <p>Год, месяц или день. Текст даты остаётся в документе.</p>
          <Popover.Close onClick={() => { returnToEditor.current = true; }}>Вернуться к тексту</Popover.Close>
        </Popover.Content></Popover.Portal>
      </Popover.Root>}
    </div>
    <div className="next-field-content" data-field-content={block.props.fieldId} ref={contentRef} />
  </section>
); } });
const schema = BlockNoteSchema.create({ blockSpecs: { resumeField: createField() }, styleSpecs: {} });
export type FieldEditorHandle = ReturnType<typeof createAdapter> & { historyEnabled: () => boolean };
type Props = { fields: readonly FieldProjection[]; callbacks: AdapterCallbacks; theme: "light" | "dark"; annotations?: readonly Annotation[] };

export const FieldEditor = forwardRef<FieldEditorHandle, Props>(function FieldEditor({ fields, callbacks, theme, annotations = [] }, ref) {
  const latest = useRef(callbacks);
  latest.current = callbacks;
  const adapter = useMemo(() => createAdapter(fields, () => latest.current), []);
  const editor = useCreateBlockNote({ schema, dictionary: ru,
    initialContent: fields.map(field => ({ id: field.fieldId, type: "resumeField", props: {
      fieldId: field.fieldId, slotId: field.slotId, label: field.label }, content: field.text })),
    disableExtensions: ["history"], extensions: [adapter.extension],
  }, []);
  useImperativeHandle(ref, () => ({ ...adapter, historyEnabled: () => Object.hasOwn(editor.extensions, "history") }), [adapter, editor]);
  return <AnnotationContext.Provider value={locateAnnotations(fields, annotations)}>
    <BlockNoteView editor={editor} theme={theme} formattingToolbar={false} sideMenu={false}
      slashMenu={false} linkToolbar={false} filePanel={false} tableHandles={false} />
  </AnnotationContext.Provider>;
});
