import { Skeleton } from "@/components/ui/skeleton";

export default function ResultLoading() {
  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="space-y-4">
        <Skeleton className="h-9 w-80" />
        <div className="flex gap-2">
          <Skeleton className="h-6 w-20 rounded-full" />
          <Skeleton className="h-6 w-16 rounded-full" />
          <Skeleton className="h-6 w-24 rounded-full" />
        </div>
      </div>

      {/* Hit Summary */}
      <div className="space-y-4">
        <Skeleton className="h-6 w-32" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      </div>

      {/* Sheet Music */}
      <div className="space-y-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-96 w-full rounded-lg" />
      </div>

      {/* Timeline */}
      <div className="space-y-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-72 w-full rounded-lg" />
      </div>

      {/* Audio */}
      <div className="space-y-4">
        <Skeleton className="h-6 w-16" />
        <Skeleton className="h-14 w-full rounded-lg" />
      </div>

      {/* Downloads */}
      <div className="flex gap-3 border-t border-border pt-6">
        <Skeleton className="h-10 w-36 rounded-md" />
        <Skeleton className="h-10 w-44 rounded-md" />
      </div>
    </div>
  );
}
