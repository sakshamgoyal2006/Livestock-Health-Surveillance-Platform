"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";
import { setReference } from "@/lib/offline";

export interface FarmRecord {
  id: string;
  name: string;
  village_name: string;
  version: number;
}

export interface AnimalRecord {
  id: string;
  farm_id: string;
  herd_id: string | null;
  tag_number: string;
  species: "CATTLE" | "BUFFALO";
  age_band: "CALF" | "YOUNG" | "ADULT" | "UNKNOWN";
}

export interface HerdRecord {
  id: string;
  farm_id: string;
  name: string;
  species: "CATTLE" | "BUFFALO";
  animal_count: number;
}

export default function RegistryPage() {
  const [farms, setFarms] = useState<FarmRecord[]>([]);
  const [animals, setAnimals] = useState<AnimalRecord[]>([]);
  const [herds, setHerds] = useState<HerdRecord[]>([]);
  const [farmName, setFarmName] = useState("");
  const [village, setVillage] = useState("");
  const [selectedFarm, setSelectedFarm] = useState("");
  const [tag, setTag] = useState("");
  const [species, setSpecies] = useState<"CATTLE" | "BUFFALO">("CATTLE");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [farmRows, animalRows, herdRows] = await Promise.all([
      apiFetch<FarmRecord[]>("/api/v1/farms"),
      apiFetch<AnimalRecord[]>("/api/v1/animals"),
      apiFetch<HerdRecord[]>("/api/v1/herds"),
    ]);
    setFarms(farmRows);
    setAnimals(animalRows);
    setHerds(herdRows);
    if (!selectedFarm && farmRows[0]) setSelectedFarm(farmRows[0].id);
    await Promise.all([
      setReference("farms", farmRows),
      setReference("animals", animalRows),
      setReference("herds", herdRows),
    ]);
  }, [selectedFarm]);

  useEffect(() => {
    refresh().catch((reason) =>
      setError(
        reason instanceof Error ? reason.message : "Could not load registry",
      ),
    );
  }, [refresh]);

  async function addFarm(event: FormEvent) {
    event.preventDefault();
    setError("");
    const farm = await apiFetch<FarmRecord>("/api/v1/farms", {
      method: "POST",
      body: JSON.stringify({
        id: crypto.randomUUID(),
        name: farmName,
        village_name: village,
        latitude: null,
        longitude: null,
        location_precision: "VILLAGE_ONLY",
      }),
    });
    setFarmName("");
    setVillage("");
    setMessage(`Farm “${farm.name}” created.`);
    setSelectedFarm(farm.id);
    await refresh();
  }

  async function addAnimal(event: FormEvent) {
    event.preventDefault();
    setError("");
    await apiFetch<AnimalRecord>("/api/v1/animals", {
      method: "POST",
      body: JSON.stringify({
        id: crypto.randomUUID(),
        farm_id: selectedFarm,
        herd_id: null,
        tag_number: tag,
        species,
        sex: "UNKNOWN",
        age_band: "ADULT",
      }),
    });
    setMessage(`Animal “${tag}” created.`);
    setTag("");
    await refresh();
  }

  async function addHerd() {
    setError("");
    await apiFetch<HerdRecord>("/api/v1/herds", {
      method: "POST",
      body: JSON.stringify({
        id: crypto.randomUUID(),
        farm_id: selectedFarm,
        name: `Herd ${herds.length + 1}`,
        species,
        animal_count: 1,
      }),
    });
    setMessage("Herd record created.");
    await refresh();
  }

  return (
    <AppShell allowedRoles={["FARMER", "FIELD_WORKER", "ADMIN"]}>
      <p className="eyebrow">Registry</p>
      <h1>Farms, herds, and animals</h1>
      {message && (
        <div className="success" role="status">
          {message}
        </div>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="split">
        <section className="card">
          <h2>Create farm</h2>
          <form onSubmit={(event) => void addFarm(event)}>
            <label className="field">
              Farm name
              <input
                data-testid="farm-name"
                required
                value={farmName}
                onChange={(event) => setFarmName(event.target.value)}
              />
            </label>
            <label className="field">
              Village
              <input
                data-testid="farm-village"
                required
                value={village}
                onChange={(event) => setVillage(event.target.value)}
              />
            </label>
            <button data-testid="create-farm">Create farm</button>
          </form>
        </section>
        <section className="card">
          <h2>Create animal or herd</h2>
          <form onSubmit={(event) => void addAnimal(event)}>
            <label className="field">
              Farm
              <select
                data-testid="animal-farm"
                required
                value={selectedFarm}
                onChange={(event) => setSelectedFarm(event.target.value)}
              >
                <option value="">Select farm</option>
                {farms.map((farm) => (
                  <option key={farm.id} value={farm.id}>
                    {farm.name} · {farm.village_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Species
              <select
                value={species}
                onChange={(event) =>
                  setSpecies(event.target.value as "CATTLE" | "BUFFALO")
                }
              >
                <option value="CATTLE">Cattle</option>
                <option value="BUFFALO">Buffalo</option>
              </select>
            </label>
            <label className="field">
              Animal tag
              <input
                data-testid="animal-tag"
                required
                value={tag}
                onChange={(event) => setTag(event.target.value)}
              />
            </label>
            <div className="actions">
              <button data-testid="create-animal" disabled={!selectedFarm}>
                Create animal
              </button>
              <button
                type="button"
                className="secondary"
                disabled={!selectedFarm}
                onClick={() => void addHerd()}
              >
                Create one-animal herd
              </button>
            </div>
          </form>
        </section>
      </div>
      <section>
        <h2>Registered subjects</h2>
        <ul className="list">
          {animals.map((animal) => (
            <li key={animal.id}>
              <strong>{animal.tag_number}</strong> · {animal.species} · animal
            </li>
          ))}
          {herds.map((herd) => (
            <li key={herd.id}>
              <strong>{herd.name}</strong> · {herd.species} ·{" "}
              {herd.animal_count} animals
            </li>
          ))}
          {!animals.length && !herds.length && (
            <li>No animals or herds yet.</li>
          )}
        </ul>
      </section>
    </AppShell>
  );
}
