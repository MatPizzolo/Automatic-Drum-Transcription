import { FileQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-6 px-4 py-24 text-center">
      <FileQuestion className="h-16 w-16 text-muted-foreground" />
      <div>
        <h1 className="text-2xl font-bold">Page not found</h1>
        <p className="mt-2 text-muted-foreground">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
      </div>
      <Button asChild>
        <Link href="/">Go Home</Link>
      </Button>
    </div>
  );
}
