import fixture from "../../../../contracts/examples/project.json" with { type: "json" };
import type { Block, Project } from "../contracts/generated/project";
import { validateContract } from "../contracts/validate";

const sample: unknown = fixture;

export function syntheticProject(): Project {
  const input: unknown = structuredClone(sample);
  if (!validateContract("project", input)) throw new Error("Invalid synthetic project fixture");
  const copy = input as Project;
  const profile = copy.views[0];
  if (!profile) throw new Error("Missing synthetic profile");
  const extra: Block[] = [
    {
      id: "job_1_prose", kind: "job_prose", revision: 1, status: "ready", visible: true,
      contentPolicyVersion: profile.contentPolicyVersion, dependencyHash: profile.dependencyHash,
      previous: null,
      state: {
        text: "Built a team from zero to five and processed up to 2000 records per day.",
        origin: "source", locked: false, factIds: ["fact_metric"], factRevisions: { fact_metric: 2 },
      },
    },
    {
      id: "job_2_prose", kind: "job_prose", revision: 1, status: "ready", visible: true,
      contentPolicyVersion: profile.contentPolicyVersion, dependencyHash: profile.dependencyHash,
      previous: null,
      state: { text: "Mentored developers.", origin: "source", locked: false,
        factIds: ["fact_user"], factRevisions: { fact_user: 1 } },
    },
    {
      id: "focus", kind: "focus", revision: 1, status: "ready", visible: true,
      contentPolicyVersion: profile.contentPolicyVersion, dependencyHash: profile.dependencyHash,
      previous: null,
      state: {
        text: "", origin: "manual", locked: false,
        factIds: ["fact_tech"], factRevisions: { fact_tech: 1 },
      },
    },
    {
      id: "education", kind: "education", revision: 1, status: "ready", visible: true,
      contentPolicyVersion: profile.contentPolicyVersion, dependencyHash: profile.dependencyHash,
      previous: null,
      state: { text: "", origin: "manual", locked: false, factIds: [], factRevisions: {} },
    },
  ];
  copy.views = [...copy.views, ...extra];
  if (copy.template === null) throw new Error("Missing synthetic template");
  copy.template = { ...copy.template, version: "1.0.0",
    packageSha256: "d081df948bfd55d107c38d40387a9758f563f9c14a9cffc4a847f44cb687b8b9", assets: [] };
  copy.renders = [];
  copy.operations = [];
  copy.proposals = [];
  if (!validateContract("project", copy)) throw new Error("Invalid expanded synthetic project");
  return copy;
}
