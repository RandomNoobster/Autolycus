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

/** Visual system for cost columns + breakdown (rails, wash, chip) per nation slot. */
export function getCostClusterTheme(slot: NationSlot) {
  if (slot === 'nation1') {
    return {
      railInset: 'inset 3px 0 0 0 rgba(56, 189, 248, 0.85)',
      railClose: 'inset -3px 0 0 0 rgba(56, 189, 248, 0.45)',
      sectionWash:
        'linear-gradient(92deg, rgba(56, 189, 248, 0.17) 0%, rgba(99, 102, 241, 0.09) 24%, rgba(99, 102, 241, 0.04) 48%, transparent 72%)',
      breakdownGradientText: 'linear-gradient(92deg, #7dd3fc 0%, #c4b5fd 100%)',
      chipBorder: '1px solid rgba(56, 189, 248, 0.35)',
      innerRule: '1px solid rgba(255, 255, 255, 0.07)',
      breakdownGroupHeadRight: '2px solid rgba(56, 189, 248, 0.52)',
      /** Softer seam where this nation’s cost block meets the other nation’s block. */
      interNationBorderRight: '1px solid rgba(56, 189, 248, 0.28)',
      interNationRailClose: 'inset -1px 0 0 0 rgba(56, 189, 248, 0.12)',
      interNationDividerLeft: '1px solid rgba(255, 255, 255, 0.045)',
      interNationRailInsetLeft: 'inset 1px 0 0 0 rgba(56, 189, 248, 0.2)',
    };
  }
  return {
    railInset: 'inset 3px 0 0 0 rgba(251, 113, 133, 0.88)',
    railClose: 'inset -3px 0 0 0 rgba(251, 113, 133, 0.5)',
    sectionWash:
      'linear-gradient(92deg, rgba(251, 113, 133, 0.17) 0%, rgba(244, 63, 94, 0.1) 26%, rgba(251, 113, 133, 0.045) 50%, transparent 74%)',
    breakdownGradientText: 'linear-gradient(92deg, #fda4af 0%, #fecdd3 100%)',
    chipBorder: '1px solid rgba(251, 113, 133, 0.4)',
    innerRule: '1px solid rgba(255, 255, 255, 0.07)',
    breakdownGroupHeadRight: '2px solid rgba(251, 113, 133, 0.52)',
    interNationBorderRight: '1px solid rgba(251, 113, 133, 0.3)',
    interNationRailClose: 'inset -1px 0 0 0 rgba(251, 113, 133, 0.14)',
    interNationDividerLeft: '1px solid rgba(255, 255, 255, 0.045)',
    interNationRailInsetLeft: 'inset 1px 0 0 0 rgba(251, 113, 133, 0.2)',
  };
}
