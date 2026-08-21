/**
 * Nation 1 = blue, Nation 2 = red (matches damage chart / form convention).
 */

export type NationSlot = 'nation1' | 'nation2';

export function nationSlotForId(nationId: number, nation1Id: number): NationSlot {
  return nationId === nation1Id ? 'nation1' : 'nation2';
}

export const NATION1_HEAD_TINT = { backgroundColor: 'rgba(34, 139, 230, 0.12)' };
export const NATION2_HEAD_TINT = { backgroundColor: 'rgba(250, 82, 82, 0.12)' };

export function headTintForSlot(slot: NationSlot): typeof NATION1_HEAD_TINT {
  return slot === 'nation1' ? NATION1_HEAD_TINT : NATION2_HEAD_TINT;
}

export const NATION1_ACCENT = 'rgb(34, 139, 230)';
export const NATION2_ACCENT = 'rgb(250, 82, 82)';

export function accentForSlot(slot: NationSlot): string {
  return slot === 'nation1' ? NATION1_ACCENT : NATION2_ACCENT;
}

/** Mantine Anchor color for nation name links on dark background */
export function mantineAnchorColorForSlot(slot: NationSlot): 'blue.1' | 'red.2' {
  return slot === 'nation1' ? 'blue.1' : 'red.2';
}

export function nationPanelBackground(slot: NationSlot): string {
  if (slot === 'nation1') {
    return 'linear-gradient(92deg, rgba(34, 139, 230, 0.16) 0%, rgba(34, 139, 230, 0.04) 48%, transparent 85%)';
  }
  return 'linear-gradient(92deg, rgba(250, 82, 82, 0.16) 0%, rgba(250, 82, 82, 0.05) 48%, transparent 85%)';
}

/** Flat fills + 1px borders for damage cost columns (no gradients or inset shadows). */
export function getCostClusterTheme(slot: NationSlot) {
  if (slot === 'nation1') {
    return {
      costBg: 'rgba(34, 139, 230, 0.1)',
      hairline: '1px solid rgba(34, 139, 230, 0.28)',
      strongEdge: '1px solid rgba(34, 139, 230, 0.45)',
    };
  }
  return {
    costBg: 'rgba(250, 82, 82, 0.1)',
    hairline: '1px solid rgba(250, 82, 82, 0.28)',
    strongEdge: '1px solid rgba(250, 82, 82, 0.45)',
  };
}
