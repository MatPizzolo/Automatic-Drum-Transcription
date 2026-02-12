import { cn } from "@/lib/utils";

interface ConfidenceBadgeProps {
  score: number;
}

export function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  const percentage = Math.round(score * 100);

  let color: string;
  let label: string;

  if (score >= 0.8) {
    color = "text-green-500 bg-green-500/10 border-green-500/30";
    label = "High";
  } else if (score >= 0.5) {
    color = "text-amber-500 bg-amber-500/10 border-amber-500/30";
    label = "Medium";
  } else {
    color = "text-red-500 bg-red-500/10 border-red-500/30";
    label = "Low";
  }

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium",
        color
      )}
    >
      <svg
        className="h-3.5 w-3.5"
        viewBox="0 0 36 36"
        aria-hidden="true"
      >
        <path
          className="stroke-current opacity-20"
          fill="none"
          strokeWidth="4"
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        />
        <path
          className="stroke-current"
          fill="none"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={`${percentage}, 100`}
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        />
      </svg>
      {label} confidence ({percentage}%)
    </div>
  );
}
