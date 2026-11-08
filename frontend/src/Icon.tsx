import type { SVGProps } from "react";

const paths = {
  chat: ["M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z", "M8 10h8M8 14h5"],
  documents: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z", "M14 2v6h6M8 13h8M8 17h5"],
  users: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8", "M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0"],
  plus: ["M12 5v14M5 12h14"],
  logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"],
  search: ["M21 21l-4.4-4.4", "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0"],
  upload: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"],
  shield: ["M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z", "m9 12 2 2 4-4"],
  refresh: ["M20 7v5h-5M4 17v-5h5M6.1 7A7 7 0 0 1 18 5l2 2M4 17l2 2a7 7 0 0 0 11.9-2"],
  send: ["m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13"],
  sparkles: ["m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4M18 4h4"],
  arrow: ["M5 12h14m-5-5 5 5-5 5"],
  check: ["m5 12 4 4L19 6"],
  building: ["M4 22V4a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v18M2 22h20M8 6h2M14 6h2M8 10h2M14 10h2M8 14h2M14 14h2M10 22v-4h4v4"],
  clock: ["M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0M12 6v6l4 2"],
  lock: ["M5 11h14v10H5V11ZM8 11V7a4 4 0 0 1 8 0v4M12 15v2"],
  menu: ["M4 6h16M4 12h16M4 18h16"],
  close: ["m6 6 12 12M6 18 18 6"],
  copy: ["M9 9h12v12H9V9ZM5 15H3V3h12v2"],
  chevron: ["m9 5 7 7-7 7"],
  grid: ["M3 3h7v7H3V3ZM14 3h7v7h-7V3ZM3 14h7v7H3v-7ZM14 14h7v7h-7v-7Z"],
} as const;
export type IconName = keyof typeof paths;
export default function Icon({ name, size = 20, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>
    {paths[name].map((path, index) => <path key={index} d={path} />)}
  </svg>;
}
