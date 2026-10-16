import { APP_NAME, BRAND_LOGO_URL } from "@/lib/constants";

/**
 * The "Anchorstone Capital Ltd" mark. A styled serif text wordmark until a
 * logo file exists — then set BRAND_LOGO_URL in lib/constants.ts and every
 * place that renders <Wordmark> switches to the image. No other changes needed.
 *
 *   tone="navy"  navy text, for white backgrounds (sidebar)
 *   tone="light" white text, for the navy sign-in panel
 *   compact      monogram only (collapsed sidebar)
 */
export function Wordmark({
  tone = "navy",
  size = "md",
  compact = false,
}: {
  tone?: "navy" | "light";
  size?: "md" | "lg";
  compact?: boolean;
}) {
  const color = tone === "light" ? "#FFFFFF" : "var(--color-brand-400)";

  if (BRAND_LOGO_URL) {
    return <img src={BRAND_LOGO_URL} alt={APP_NAME} style={{ height: compact ? 32 : size === "lg" ? 64 : 36, width: "auto" }} />;
  }

  if (compact) {
    return (
      <span
        aria-label={APP_NAME}
        className="d-inline-flex align-items-center justify-content-center"
        style={{
          width: 36,
          height: 36,
          borderRadius: 8,
          background: tone === "light" ? "#FFFFFF" : "var(--color-brand-400)",
          color: tone === "light" ? "var(--color-brand-400)" : "#FFFFFF",
          fontFamily: "var(--font-wordmark)",
          fontWeight: 700,
          fontSize: 20,
          lineHeight: 1,
        }}
      >
        A
      </span>
    );
  }

  const big = size === "lg";
  return (
    <span aria-label={APP_NAME} style={{ display: "inline-block", color, fontFamily: "var(--font-wordmark)", lineHeight: 1.05 }}>
      <span style={{ display: "block", fontWeight: 700, fontSize: big ? 44 : 21, letterSpacing: "0.005em" }}>Anchorstone</span>
      <span
        style={{
          display: "block",
          fontWeight: 600,
          fontSize: big ? 15 : 10,
          letterSpacing: big ? "0.32em" : "0.28em",
          marginTop: big ? 8 : 3,
          opacity: tone === "light" ? 0.85 : 0.8,
          textTransform: "uppercase",
        }}
      >
        Capital Ltd
      </span>
    </span>
  );
}
