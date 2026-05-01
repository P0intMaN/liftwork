import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Server } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/providers/AuthProvider";
import { relTime } from "@/lib/format";

export default function ClustersPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const clusters = useQuery({ queryKey: ["clusters"], queryFn: api.listClusters });
  const create = useMutation({
    mutationFn: api.createCluster,
    onSuccess: () => {
      toast.success("Cluster registered");
      queryClient.invalidateQueries({ queryKey: ["clusters"] });
      setOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <>
      <PageHeader
        title="Clusters"
        subtitle="Kubernetes targets liftwork can deploy to."
        actions={
          <Button onClick={() => setOpen(true)} disabled={user?.role !== "admin"}>
            <Plus className="h-4 w-4" /> Register cluster
          </Button>
        }
      />
      <section className="px-8 py-6">
        {clusters.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : clusters.data?.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {clusters.data.map((c) => (
              <Card key={c.id} className="p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-semibold tracking-tight">{c.display_name}</p>
                    <p className="font-mono text-xs text-muted-foreground">{c.name}</p>
                  </div>
                  <StatusBadge status={c.status} />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <div>
                    <p className="text-[11px] uppercase tracking-wider">Default ns</p>
                    <p className="mt-0.5 text-foreground">{c.default_namespace}</p>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wider">Mode</p>
                    <p className="mt-0.5 text-foreground">{c.in_cluster ? "in-cluster SA" : "kubeconfig"}</p>
                  </div>
                </div>
                <p className="mt-3 text-[11px] text-muted-foreground">added {relTime(c.created_at)}</p>
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid place-items-center rounded-xl border border-dashed border-border p-16 text-center">
            <Server className="mb-3 h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">No clusters registered</p>
            {user?.role === "admin" ? (
              <Button className="mt-4" onClick={() => setOpen(true)}>
                <Plus className="h-4 w-4" /> Register your first cluster
              </Button>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">ask an admin to register one</p>
            )}
          </div>
        )}
      </section>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Register cluster</DialogTitle>
            <DialogDescription>
              The name must match the kubeconfig context (or service-account if running in-cluster).
            </DialogDescription>
          </DialogHeader>
          <ClusterForm
            submitting={create.isPending}
            onCreate={(input) => create.mutate(input)}
            onCancel={() => setOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

function ClusterForm({
  submitting,
  onCreate,
  onCancel,
}: {
  submitting: boolean;
  onCreate: (input: { name: string; display_name: string; default_namespace: string }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("kind-kubedeploy-dev");
  const [displayName, setDisplayName] = useState("Local kind cluster");
  const [ns, setNs] = useState("default");
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        onCreate({ name, display_name: displayName, default_namespace: ns });
      }}
    >
      <div className="space-y-1.5">
        <Label>Name (kubeconfig context)</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label>Display name</Label>
        <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label>Default namespace</Label>
        <Input value={ns} onChange={(e) => setNs(e.target.value)} />
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : "Register"}
        </Button>
      </DialogFooter>
    </form>
  );
}
