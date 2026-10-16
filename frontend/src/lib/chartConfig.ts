import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
  type ChartOptions,
} from "chart.js";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

/** Read a CSS custom property so charts follow the theme tokens in globals.css. */
export function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function flowColors() {
  return {
    deposit: cssVar("--color-chart-deposit", "#1A2060"),
    withdrawal: cssVar("--color-chart-withdrawal", "#9AA0D6"),
  };
}

export function baseChartOptions(): ChartOptions<"bar"> {
  const grid = cssVar("--color-chart-grid", "#EEEFF7");
  const label = cssVar("--color-chart-label", "#6C7088");
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { mode: "index", intersect: false },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: label, font: { size: 11 } } },
      y: { grid: { color: grid }, ticks: { color: label, font: { size: 11 } }, beginAtZero: true },
    },
  };
}
