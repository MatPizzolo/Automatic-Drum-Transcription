import { AlertTriangle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { WARNING_MESSAGES } from "@/lib/constants";

interface WarningsBannerProps {
  warnings: string[];
}

export function WarningsBanner({ warnings }: WarningsBannerProps) {
  if (!warnings || warnings.length === 0) return null;

  return (
    <Alert className="border-amber-500/50 bg-amber-500/10 text-amber-600 dark:text-amber-400">
      <AlertTriangle className="h-4 w-4 text-amber-500" />
      <AlertTitle>Heads up</AlertTitle>
      <AlertDescription>
        <ul className="mt-1 list-disc pl-4 text-sm">
          {warnings.map((w) => (
            <li key={w}>{WARNING_MESSAGES[w] || w}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}
