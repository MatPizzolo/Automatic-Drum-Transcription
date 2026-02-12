import { Skeleton } from "@/components/ui/skeleton";

export default function ProcessingLoading() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
      <div className="space-y-8">
        <div className="text-center space-y-2">
          <Skeleton className="mx-auto h-8 w-64" />
          <Skeleton className="mx-auto h-5 w-96" />
        </div>
        <div className="flex justify-between gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex flex-1 flex-col items-center gap-2">
              <Skeleton className="h-10 w-10 rounded-full" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
        <Skeleton className="h-2 w-full rounded-full" />
      </div>
    </div>
  );
}
