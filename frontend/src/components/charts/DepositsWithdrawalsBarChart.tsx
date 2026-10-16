import { Bar } from "react-chartjs-2";
import type { ChartData, ChartOptions } from "chart.js";
import { baseChartOptions, flowColors } from "@/lib/chartConfig";
import { formatKES, formatKESCompact } from "@/lib/utils";

interface Props {
  labels: string[];
  deposits: number[];
  withdrawals: number[];
  height?: number;
}

export function DepositsWithdrawalsBarChart({ labels, deposits, withdrawals, height = 260 }: Props) {
  const colors = flowColors();
  const data: ChartData<"bar"> = {
    labels,
    datasets: [
      { label: "Deposits", data: deposits, backgroundColor: colors.deposit, borderRadius: 3, barPercentage: 0.7 },
      { label: "Withdrawals", data: withdrawals, backgroundColor: colors.withdrawal, borderRadius: 3, barPercentage: 0.7 },
    ],
  };

  const base = baseChartOptions();
  const options: ChartOptions<"bar"> = {
    ...base,
    plugins: {
      ...base.plugins,
      tooltip: {
        ...base.plugins?.tooltip,
        callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatKES(ctx.parsed.y)}` },
      },
    },
    scales: {
      ...base.scales,
      y: {
        ...base.scales?.y,
        ticks: { ...(base.scales?.y?.ticks ?? {}), callback: (v) => formatKESCompact(Number(v)) },
      },
    },
  };

  return (
    <div style={{ position: "relative", height }}>
      <Bar data={data} options={options} aria-label="Deposits and withdrawals by month" />
    </div>
  );
}
