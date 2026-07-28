import { Affix, Button, Transition } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconArrowDown } from '@tabler/icons-react';
import { useEffect, useState, type RefObject } from 'react';

import { useMobileNavOpen } from '@/components/layout/MobileNavOpenContext';

type JumpToTableButtonProps = {
  targetRef: RefObject<HTMLElement | null>;
};

/** Mobile-only floating control that scrolls to the results table. */
export function JumpToTableButton({ targetRef }: JumpToTableButtonProps) {
  const isMobile = useMediaQuery('(max-width: 48em)', false, {
    getInitialValueInEffect: false,
  });
  const mobileNavOpen = useMobileNavOpen();
  // Only when the table is still below the fold — not in view, and not scrolled past.
  const [tableBelowFold, setTableBelowFold] = useState(false);

  useEffect(() => {
    const el = targetRef.current;
    if (!el || !isMobile) {
      setTableBelowFold(false);
      return;
    }

    const update = () => {
      const rect = el.getBoundingClientRect();
      // Header clearance (~56px): treat as "reached" once the section top is near the header.
      setTableBelowFold(rect.top > 72);
    };

    update();
    const observer = new IntersectionObserver(update, {
      root: null,
      threshold: [0, 0.01, 0.05, 0.1, 1],
    });
    observer.observe(el);
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [targetRef, isMobile]);

  if (!isMobile) return null;

  return (
    // Centered just above the 44px sticky footer.
    <Affix
      position={{ bottom: 46, left: 0, right: 0 }}
      zIndex={200}
      style={{ display: 'flex', justifyContent: 'center', pointerEvents: 'none' }}
    >
      <Transition transition="slide-up" mounted={tableBelowFold && !mobileNavOpen}>
        {(styles) => (
          <Button
            style={{ ...styles, pointerEvents: 'auto' }}
            size="md"
            radius="xl"
            color="orange"
            leftSection={<IconArrowDown size={18} />}
            onClick={() => {
              targetRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }}
          >
            Jump to table
          </Button>
        )}
      </Transition>
    </Affix>
  );
}
