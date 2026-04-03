import { createTheme, MantineColorsTuple } from '@mantine/core';

// Custom orange color matching the P&W / Autolycus aesthetic
const autolycusOrange: MantineColorsTuple = [
  '#fff4e6',
  '#ffe8cc',
  '#ffd8a8',
  '#ffc078',
  '#ffa94d',
  '#ff922b',
  '#fd7e14',
  '#f76707',
  '#e8590c',
  '#d9480f',
];

export const theme = createTheme({
  primaryColor: 'autolycusOrange',
  colors: {
    autolycusOrange,
  },
  fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
  headings: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
    fontWeight: '600',
  },
  defaultRadius: 'md',
  components: {
    Anchor: {
      defaultProps: {
        c: 'autolycusOrange.6',
      },
    },
    Table: {
      defaultProps: {
        striped: true,
        highlightOnHover: true,
      },
    },
  },
});
