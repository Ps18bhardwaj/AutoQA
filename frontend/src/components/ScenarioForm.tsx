import { useState } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ScenarioValues {
  url: string;
  scenario: string;
  maxSteps: number;
}

const SAMPLES: { label: string; url: string; scenario: string }[] = [
  {
    label: "SauceDemo: login + cheapest item",
    url: "https://www.saucedemo.com",
    scenario: "Log in as standard_user with password secret_sauce, add the cheapest item to the cart, and verify the cart badge shows 1.",
  },
  {
    label: "SauceDemo (problem_user): images",
    url: "https://www.saucedemo.com",
    scenario: "Log in as problem_user with password secret_sauce and check that every product image on the inventory page is correct and loads.",
  },
  {
    label: "the-internet: login works",
    url: "https://the-internet.herokuapp.com/login",
    scenario: "Log in with username tomsmith and password SuperSecretPassword! and confirm the secure area is reached.",
  },
  {
    label: "the-internet: broken images",
    url: "https://the-internet.herokuapp.com/broken_images",
    scenario: "Check the page for broken images — every image should load.",
  },
  {
    label: "Local demo shop: total updates",
    url: "http://localhost:8003/demo/shop.html",
    scenario: "Add an item to the cart. The cart total must update to reflect the added item's price.",
  },
];

export function ScenarioForm({
  onRun,
  disabled,
}: {
  onRun: (values: ScenarioValues) => void;
  disabled?: boolean;
}) {
  const [url, setUrl] = useState("");
  const [scenario, setScenario] = useState("");
  const [maxSteps, setMaxSteps] = useState(12);

  const canRun = url.trim() && scenario.trim() && !disabled;

  return (
    <div className="mx-auto mt-6 w-full max-w-xl">
      <div className="mb-4 text-center">
        <h2 className="text-lg font-semibold">Test a website in plain English</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Point AutoQA at a URL and describe the flow to check. It drives a real
          browser, verifies the scenario, and files a bug report with screenshots.
        </p>
      </div>

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Start URL</label>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.saucedemo.com"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Test scenario</label>
          <textarea
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            rows={3}
            placeholder="Log in as standard_user / secret_sauce, add the cheapest item to the cart, the cart badge must show 1."
            className="w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs font-medium text-muted-foreground">Max steps</label>
          <select
            value={maxSteps}
            onChange={(e) => setMaxSteps(Number(e.target.value))}
            className="rounded-md border border-border bg-background px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-ring"
          >
            <option value={8}>8</option>
            <option value={12}>12</option>
            <option value={20}>20</option>
          </select>
          <Button
            className="ml-auto"
            disabled={!canRun}
            onClick={() => onRun({ url: url.trim(), scenario: scenario.trim(), maxSteps })}
          >
            <Play className="h-4 w-4" /> Run QA
          </Button>
        </div>
      </div>

      <div className="mt-5">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Try a sample:</p>
        <div className="flex flex-wrap gap-2">
          {SAMPLES.map((s) => (
            <button
              key={s.label}
              onClick={() => { setUrl(s.url); setScenario(s.scenario); }}
              className="rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
