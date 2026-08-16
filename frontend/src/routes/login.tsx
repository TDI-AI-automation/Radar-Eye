import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Shield } from "lucide-react";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [{ title: "Sign In — SENTINEL C2" }],
  }),
  component: LoginPage,
});

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  async function onSubmit(values: LoginFormValues) {
    setSubmitError(null);
    try {
      await login(values.username, values.password);
      await navigate({ to: "/" });
    } catch {
      setSubmitError("Invalid username or password.");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="hud-panel hud-corner w-full max-w-sm p-8">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="relative flex h-12 w-12 items-center justify-center rounded border border-primary/50 bg-primary/10">
            <Shield className="h-6 w-6 text-primary" />
            <span className="absolute inset-0 rounded animate-pulse-cyan" />
          </div>
          <div>
            <div className="font-mono text-xs uppercase tracking-[0.3em] text-primary">
              SENTINEL C2
            </div>
            <div className="mt-1 text-[10px] text-muted-foreground">
              Operator authentication required
            </div>
          </div>
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="username"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="font-mono text-[10px] uppercase tracking-widest">
                    Username
                  </FormLabel>
                  <FormControl>
                    <Input autoComplete="username" autoFocus {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="font-mono text-[10px] uppercase tracking-widest">
                    Password
                  </FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="current-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {submitError ? (
              <p className="text-glow-red font-mono text-xs" role="alert">
                {submitError}
              </p>
            ) : null}

            <Button
              type="submit"
              className="w-full font-mono text-xs uppercase tracking-widest"
              disabled={form.formState.isSubmitting}
            >
              {form.formState.isSubmitting ? "Authenticating…" : "Sign In"}
            </Button>
          </form>
        </Form>
      </div>
    </div>
  );
}
