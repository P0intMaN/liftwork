import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, Boxes } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { relTime } from "@/lib/format";

export default function ApplicationsPage() {
  const apps = useQuery({ queryKey: ["applications"], queryFn: api.listApplications });
  const clusters = useQuery({ queryKey: ["clusters"], queryFn: api.listClusters });
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const create = useMutation({
    mutationFn: api.createApplication,
    onSuccess: () => {
      toast.success("Application created");
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      setOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <>
      <PageHeader
        title="Applications"
        subtitle="Repos liftwork is connected to. A push triggers build → deploy."
        actions={
          <Button onClick={() => setOpen(true)} disabled={!clusters.data?.length}>
            <Plus className="h-4 w-4" /> New application
          </Button>
        }
      />
      <section className="px-8 py-6">
        {apps.isLoading ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        ) : apps.data?.length ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {apps.data.map((app) => (
              <Card
                key={app.id}
                className="group p-5 transition-colors hover:border-primary/40"
              >
                <Link to={`/applications/${app.id}`} className="block">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-semibold tracking-tight">{app.display_name}</p>
                      <p className="font-mono text-xs text-muted-foreground">
                        {app.repo_owner}/{app.repo_name}
                      </p>
                    </div>
                    {app.auto_deploy && <Badge variant="secondary">auto-deploy</Badge>}
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="rounded-md bg-secondary px-2 py-0.5">
                      ns: {app.namespace}
                    </span>
                    <span className="rounded-md bg-secondary px-2 py-0.5">
                      {app.default_branch}
                    </span>
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    created {relTime(app.created_at)}
                  </p>
                </Link>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState onCreate={() => setOpen(true)} disabled={!clusters.data?.length} />
        )}
      </section>

      <NewApplicationDialog
        open={open}
        onOpenChange={setOpen}
        clusters={clusters.data ?? []}
        onCreate={(input) => create.mutate(input)}
        submitting={create.isPending}
      />
    </>
  );
}

function EmptyState({ onCreate, disabled }: { onCreate: () => void; disabled: boolean }) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-border p-16 text-center">
      <Boxes className="mb-3 h-8 w-8 text-muted-foreground" />
      <p className="text-sm font-medium">No applications yet</p>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">
        {disabled
          ? "Add a cluster on the Clusters page first, then come back to register a repo."
          : "Connect your first repo — language is auto-detected, no Dockerfile required."}
      </p>
      <Button className="mt-4" onClick={onCreate} disabled={disabled}>
        <Plus className="h-4 w-4" /> New application
      </Button>
    </div>
  );
}

function NewApplicationDialog({
  open,
  onOpenChange,
  clusters,
  onCreate,
  submitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clusters: { id: string; name: string; display_name: string }[];
  onCreate: (input: {
    slug: string;
    display_name: string;
    repo_url: string;
    repo_owner: string;
    repo_name: string;
    default_branch: string;
    cluster_id: string;
    namespace: string;
    image_repository: string;
    auto_deploy: boolean;
    app_port: number;
    health_check_path: string;
    replicas: number;
  }) => void;
  submitting: boolean;
}) {
  const [slug, setSlug] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [namespace, setNamespace] = useState("");
  const [clusterId, setClusterId] = useState(clusters[0]?.id ?? "");
  const [port, setPort] = useState("8080");
  const [healthPath, setHealthPath] = useState("/healthz");
  const [replicas, setReplicas] = useState("1");

  function parseRepo(url: string) {
    // Accept https or ssh GitHub URLs and pull owner/name
    const m = url.match(/(?:github\.com[/:])([\w.-]+)\/([\w.-]+?)(?:\.git)?$/);
    return m ? { owner: m[1]!, name: m[2]! } : null;
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseRepo(repoUrl);
    if (!parsed) {
      toast.error("repo_url should look like https://github.com/owner/repo.git");
      return;
    }
    if (!clusterId) {
      toast.error("pick a cluster");
      return;
    }
    onCreate({
      slug,
      display_name: displayName || `${parsed.owner}/${parsed.name}`,
      repo_url: repoUrl,
      repo_owner: parsed.owner,
      repo_name: parsed.name,
      default_branch: "main",
      cluster_id: clusterId,
      namespace: namespace || slug,
      image_repository: `liftwork/${slug}`,
      auto_deploy: true,
      app_port: Number(port) || 8080,
      health_check_path: healthPath || "/healthz",
      replicas: Number(replicas) || 1,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect a repository</DialogTitle>
          <DialogDescription>
            Liftwork detects the language and renders a Dockerfile if you don't commit one.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-3" onSubmit={onSubmit}>
          <Field
            label="Slug"
            hint="lowercase, hyphens only"
            value={slug}
            onChange={setSlug}
            placeholder="my-api"
            pattern="[a-z0-9-]{2,}"
          />
          <Field
            label="Display name"
            value={displayName}
            onChange={setDisplayName}
            placeholder="My API (optional)"
          />
          <Field
            label="Repo URL"
            value={repoUrl}
            onChange={setRepoUrl}
            placeholder="https://github.com/owner/repo.git"
          />
          <Field
            label="Target namespace"
            hint="defaults to the slug"
            value={namespace}
            onChange={setNamespace}
            placeholder="my-api"
          />
          <div className="grid grid-cols-3 gap-3">
            <Field label="Port" hint="containerPort + Service" value={port} onChange={setPort} placeholder="8080" />
            <Field label="Health path" hint="readiness/liveness" value={healthPath} onChange={setHealthPath} placeholder="/healthz" />
            <Field label="Replicas" value={replicas} onChange={setReplicas} placeholder="1" />
          </div>
          <div className="space-y-2">
            <Label>Cluster</Label>
            <select
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={clusterId}
              onChange={(e) => setClusterId(e.target.value)}
            >
              {clusters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name} ({c.name})
                </option>
              ))}
            </select>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Connecting…" : "Connect"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  hint,
  value,
  onChange,
  placeholder,
  pattern,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  pattern?: string;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <Label>{label}</Label>
        {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
      </div>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        pattern={pattern}
        required={label === "Slug" || label === "Repo URL"}
      />
    </div>
  );
}
