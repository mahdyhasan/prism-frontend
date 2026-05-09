import { redirect } from "next/navigation";

// Root → redirect to login. The dashboard shell handles authenticated routing.
export default function RootPage() {
  redirect("/login");
}
