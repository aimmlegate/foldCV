export function limitsEditToSelection(message: string): boolean {
  const positive = /(?:(?:только|лишь)\s+(?:в\s+)?(?:выделенн\p{L}*|(?:этот|данный)\s+фрагмент)|(?:only|just)\s+(?:in\s+)?(?:the\s+)?(?:select\p{L}*|this\s+(?:fragment|passage|block)))/giu;
  return [...message.matchAll(positive)].some(match => {
    const prefix = message.slice(0, match.index).trimEnd();
    return !/(?:\bnot|не)\s*$/iu.test(prefix);
  });
}
