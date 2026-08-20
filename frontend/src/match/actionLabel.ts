export function actionLabel(action?: Record<string, unknown>) {
  if (!action) return 'Waiting for an action';
  if (action.type === 'offer') {
    const split = action.split as Record<string, number> | undefined;
    return `Offers to keep ${Object.entries(split ?? {})
      .map(([item, quantity]) => `${quantity} ${item}`)
      .join(', ')}`;
  }
  if (action.type === 'say') return String(action.text ?? 'Speaks');
  if (action.type === 'end_interview') return 'Ends the interview';
  return String(action.type ?? 'Unknown action');
}
