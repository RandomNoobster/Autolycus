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
  const [tableInView, setTableInView] = useState(false);

  useEffect(() => {
    const el = targetRef.current;
    if (!el || !isMobile) {
      setTableInView(false);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => setTableInView(entry.isIntersecting),
      {
        // Hide once the table heading area is reasonably on screen (header/footer safe areas).
        root: null,
        threshold: 0.05,
        rootMargin: '-64px 0px -48px 0px',
      }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [targetRef, isMobile]);

  if (!isMobile) return null;

  return (
    // Centered just above the 44px sticky footer.
    <Affix
      position={{ bottom: 46, left: 0, right: 0 }}
      zIndex={200}
      style={{ display: 'flex', justifyContent: 'center', pointerEvents: 'none' }}
    >
      <Transition transition="slide-up" mounted={!tableInView && !mobileNavOpen}>
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
