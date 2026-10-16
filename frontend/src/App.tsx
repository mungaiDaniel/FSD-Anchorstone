import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { router } from "@/routes";
import { AuthProvider } from "@/context/AuthContext";
import { UIProvider } from "@/context/UIContext";

export default function App() {
  return (
    <AuthProvider>
      <UIProvider>
        <RouterProvider router={router} />
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "var(--color-bg-overlay)",
              border: "1px solid var(--color-border-subtle)",
              color: "var(--color-text-primary)",
              fontSize: "13px",
            },
          }}
        />
      </UIProvider>
    </AuthProvider>
  );
}
