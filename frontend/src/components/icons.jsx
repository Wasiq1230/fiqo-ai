/**
 * Shared SVG icon set + tiny presentational helpers.
 *
 * All icons are inline SVG (no icon-font / no external dependency) so the
 * bundle stays small and nothing is fetched at runtime.
 */

export const Ico = ({ path, size = 18, strokeWidth = 1.6, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
    focusable="false"
  >
    {Array.isArray(path)
      ? path.map((d, i) => <path key={i} d={d} />)
      : <path d={path} />}
  </svg>
);

export const Icons = {
  dashboard: "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
  summary:   "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8",
  quiz:      "M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01",
  flashcard: "M2 8h20v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2zM2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v2M12 12v4M10 14h4",
  viva:      "M12 1a3 3 0 0 1 3 3v8a3 3 0 0 1-6 0V4a3 3 0 0 1 3-3zm-1 16.93A8 8 0 0 1 4 12H2a10 10 0 0 0 9 9.93V23h2v-1.07A10 10 0 0 0 22 12h-2a8 8 0 0 1-7 7.93z",
  plan:      "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
  notes:     "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z",
  chat:      "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 0 2 2z",
  search:    "m21 21-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0z",
  history:   "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5M12 7v5l4 2",
  upload:    "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  attach:    "M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48",
  send:      "M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z",
  mic:       "M12 1a3 3 0 0 1 3 3v8a3 3 0 0 1-6 0V4a3 3 0 0 1 3-3z",
  volume:    ["M11 5 6 9H2v6h4l5 4V5z", "M19.07 4.93a10 10 0 0 1 0 14.14", "M15.54 8.46a5 5 0 0 1 0 7.07"],
  stop:      "M9 9h6v6H9z",
  download:  "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  star:      "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z",
  logout:    "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  close:     "M18 6 6 18M6 6l12 12",
  check:     "M20 6 9 17l-5-5",
  sparkle:   "M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z",
  file:      "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6",
  chevron:   "M9 18l6-6-6-6",
  plus:      "M12 5v14M5 12h14",
  grid:      "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
  menu:      "M3 12h18M3 6h18M3 18h18",
  shield:    "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  message:   "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 0 2 2z",
  users:     "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  eye:       "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  eyeOff:    "m17.94 17.94-1.42 1.42M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM2 2l20 20",
};

export const getInitials = (name = "") =>
  name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase() || "U";

/** Small inline spinner used inside buttons. */
export const Spinner = ({ size = 15 }) => (
  <span
    className="um-loader"
    style={{ width: size, height: size }}
    role="status"
    aria-label="Loading"
  />
);
