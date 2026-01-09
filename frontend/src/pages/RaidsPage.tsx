/**
 * Raids Page
 *
 * Displays raid targets with token authentication.
 */

import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Badge,
  Paper,
  Grid,
  NumberInput,
  Select,
  Switch,
  Button,
  Tooltip,
  ActionIcon,
  Autocomplete,
  Anchor,
  Alert,
  Loader,
  TextInput,
  Divider,
} from '@mantine/core';
import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { IconQuestionMark, IconSearch, IconX, IconAlertCircle, IconBrandDiscord, IconDownload } from '@tabler/icons-react';
import { useDebouncedValue } from '@mantine/hooks';
import { IconPlus, IconCopy, IconTrash, IconPencil } from '@tabler/icons-react';
import type {
  MRT_ColumnFiltersState,
  MRT_ColumnOrderState,
  MRT_DensityState,
  MRT_VisibilityState,
} from 'mantine-react-table';

import { fetchRaids, searchAlliances } from '@/api';
import { useUrlParams, useNationId } from '@/hooks';
import { RaidsTable } from '@/components/raids';
import { TokenError, LoadingState, ErrorState, NationIdField } from '@/components/common';
import type { ApiError } from '@/types';

type TableTemplateSettings = {
  columnVisibility: MRT_VisibilityState;
  columnOrder: MRT_ColumnOrderState;
  density: MRT_DensityState;
  columnFilters: MRT_ColumnFiltersState;
};

type TableTemplate = {
  id: string;
  name: string;
  builtIn: boolean;
  settings: TableTemplateSettings;
};

const TEMPLATE_STORAGE_KEY = 'autolycus-raids-templates-v1';
const ACTIVE_TEMPLATE_STORAGE_KEY = 'autolycus-raids-active-template';

const PROVEN_TARGET_TEMPLATE_SETTINGS: TableTemplateSettings = {
  columnVisibility: {
    actions: true,
    id: false,
    nationName: true,
    leaderName: false,
    allianceName: true,
    alliancePosition: true,
    numCities: true,
    color: true,
    nationLoot: true,
    daysInactive: true,
    monetaryNetIncome: false,
    netCashIncome: false,
    taxable: false,
    treasures: false,
    defSlots: true,
    timeSinceWar: true,
    soldiers: false,
    tanks: false,
    aircraft: false,
    ships: false,
    missiles: false,
    nukes: false,
    groundWin: true,
    airWin: true,
    navalWin: true,
    totalWin: true,
  },
  columnOrder: [
    'id',
    'nationName',
    'leaderName',
    'allianceName',
    'alliancePosition',
    'numCities',
    'color',
    'nationLoot',
    'daysInactive',
    'monetaryNetIncome',
    'netCashIncome',
    'taxable',
    'treasures',
    'defSlots',
    'timeSinceWar',
    'soldiers',
    'tanks',
    'aircraft',
    'ships',
    'missiles',
    'nukes',
    'groundWin',
    'airWin',
    'navalWin',
    'totalWin',
    'actions',
    'mrt-row-spacer',
  ],
  density: 'xs',
  columnFilters: [],
};

const UNREAPED_FRUIT_TEMPLATE_SETTINGS: TableTemplateSettings = {
  columnVisibility: {
    actions: true,
    id: false,
    nationName: true,
    leaderName: false,
    allianceName: true,
    alliancePosition: true,
    numCities: true,
    color: true,
    nationLoot: true,
    daysInactive: true,
    monetaryNetIncome: true,
    netCashIncome: true,
    taxable: true,
    treasures: true,
    defSlots: true,
    timeSinceWar: true,
    soldiers: false,
    tanks: false,
    aircraft: false,
    ships: false,
    missiles: false,
    nukes: false,
    groundWin: true,
    airWin: true,
    navalWin: true,
    totalWin: true,
  },
  columnOrder: [
    'id',
    'nationName',
    'leaderName',
    'allianceName',
    'alliancePosition',
    'numCities',
    'color',
    'nationLoot',
    'daysInactive',
    'monetaryNetIncome',
    'netCashIncome',
    'taxable',
    'treasures',
    'defSlots',
    'timeSinceWar',
    'soldiers',
    'tanks',
    'aircraft',
    'ships',
    'missiles',
    'nukes',
    'groundWin',
    'airWin',
    'navalWin',
    'totalWin',
    'actions',
    'mrt-row-spacer',
  ],
  density: 'xs',
  columnFilters: [
    { id: 'groundWin', value: 70 },
    { id: 'taxable', value: false },
    { id: 'monetaryNetIncome', value: 1e6 },
    { id: 'daysInactive', value: 7 }
  ],
};

const BUILT_IN_TEMPLATES: TableTemplate[] = [
  {
    id: 'builtin-proven',
    name: "Already Proven Targets",
    builtIn: true,
    settings: cloneSettings(PROVEN_TARGET_TEMPLATE_SETTINGS),
  },
  {
    id: 'builtin-unreaped',
    name: 'Unreaped Fruits',
    builtIn: true,
    settings: {
      ...cloneSettings(UNREAPED_FRUIT_TEMPLATE_SETTINGS),
      // You can tweak this template's order/visibility later if desired.
    },
  },
];

const MAPPED_COLUMN_IDS = new Set([
  'allianceName',
  'beigeTurns',
  'defSlots',
  'daysInactive',
  'alliancePosition',
  'nationLoot',
]);

function cloneSettings(settings: TableTemplateSettings): TableTemplateSettings {
  return {
    columnVisibility: { ...settings.columnVisibility },
    columnOrder: [...settings.columnOrder],
    density: settings.density,
    columnFilters: JSON.parse(JSON.stringify(settings.columnFilters || [])),
  };
}

function loadCustomTemplates(): TableTemplate[] {
  try {
    const raw = localStorage.getItem(TEMPLATE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as TableTemplate[];
    return parsed
      .filter((t) => !t.builtIn)
      .map((t) => ({ ...t, settings: cloneSettings(t.settings) }));
  } catch (error) {
    console.warn('Failed to load raid table templates', error);
    return [];
  }
}

function persistCustomTemplates(customTemplates: TableTemplate[]): void {
  try {
    localStorage.setItem(TEMPLATE_STORAGE_KEY, JSON.stringify(customTemplates));
  } catch (error) {
    console.warn('Failed to save raid table templates', error);
  }
}

function loadActiveTemplateId(fallbackId: string): string {
  try {
    const stored = localStorage.getItem(ACTIVE_TEMPLATE_STORAGE_KEY);
    if (stored) return stored;
  } catch (error) {
    console.warn('Failed to read active template id', error);
  }
  return fallbackId;
}

function mergeColumnFilters(
  base: MRT_ColumnFiltersState,
  overrides: MRT_ColumnFiltersState
): MRT_ColumnFiltersState {
  const map = new Map<string, any>();
  base.forEach((f) => map.set(f.id, f.value));
  overrides.forEach((f) => map.set(f.id, f.value));
  return Array.from(map.entries()).map(([id, value]) => ({ id, value }));
}

function areSettingsEqual(a: TableTemplateSettings, b: TableTemplateSettings): boolean {
  return (
    JSON.stringify(a.columnVisibility) === JSON.stringify(b.columnVisibility) &&
    JSON.stringify(a.columnOrder) === JSON.stringify(b.columnOrder) &&
    a.density === b.density &&
    JSON.stringify(a.columnFilters) === JSON.stringify(b.columnFilters)
  );
}

function buildInitialTemplates(): TableTemplate[] {
  const builtIns = BUILT_IN_TEMPLATES.map((t) => ({ ...t, settings: cloneSettings(t.settings) }));
  const custom = loadCustomTemplates();
  return [...builtIns, ...custom];
}

export function RaidsPage() {
  const { token, initialColumnFilters, initialSorting } = useUrlParams();
  const { nationId: savedNationId, parseNationId } = useNationId();
  const [searchParams, setSearchParams] = useSearchParams();
  const [appliedNationId, setAppliedNationId] = useState(savedNationId);
  const [draftNationId, setDraftNationId] = useState(savedNationId);

  const parseNumber = (key: string): number | undefined => {
    const val = searchParams.get(key);
    if (val === null || val === '') return undefined;
    const num = Number(val);
    return Number.isNaN(num) ? undefined : num;
  };

  const parseBoolean = (key: string): boolean | undefined => {
    const val = searchParams.get(key);
    if (val === null) return undefined;
    return val === 'true' || val === '1';
  };

  // Active filters from URL (used for API call)
  const activeFilters = {
    alliance: searchParams.get('alliance') || undefined,
    beige: parseBoolean('beige'),
    maxWars: parseNumber('maxWars'),
    inactiveMinDays: parseNumber('inactiveMinDays'),
    scope: (searchParams.get('scope') as 'all' | 'apps_or_none' | 'no_alliance' | null) || undefined,
    minBeigeLoot: parseNumber('minBeigeLoot'),
    performance: parseBoolean('performance'),
    scoreMode: searchParams.get('scoreMode') || 'custom',
    yourScore: parseNumber('yourScore'),
    minScore: parseNumber('minScore'),
    maxScore: parseNumber('maxScore'),
  };

  // Local draft state for filters (before submit)
  const [draftFilters, setDraftFilters] = useState({
    alliance: activeFilters.alliance || '',
    beige: activeFilters.beige === true ? 'only' : activeFilters.beige === false ? 'hide' : 'all',
    maxWars: activeFilters.maxWars?.toString() || 'all',
    inactiveMinDays: activeFilters.inactiveMinDays?.toString() || 'none',
    scope: activeFilters.scope || 'all',
    minBeigeLoot: activeFilters.minBeigeLoot?.toString() || '0',
    performance: activeFilters.performance ?? false,
    scoreMode: activeFilters.scoreMode || (savedNationId ? 'yours' : 'custom'),
    yourScore: activeFilters.yourScore?.toString() || '',
    minScore: activeFilters.minScore?.toString() || '',
    maxScore: activeFilters.maxScore?.toString() || '',
  });

  const [templates, setTemplates] = useState<TableTemplate[]>(() => buildInitialTemplates());
  const [activeTemplateId, setActiveTemplateId] = useState<string>(() => {
    const initial = buildInitialTemplates();
    const fallback = initial[0]?.id || 'builtin-proven';
    const saved = loadActiveTemplateId(fallback);
    return initial.find((t) => t.id === saved)?.id || fallback;
  });

  const activeTemplate = useMemo(
    () => templates.find((t) => t.id === activeTemplateId) || templates[0],
    [templates, activeTemplateId]
  );

  const [columnVisibility, setColumnVisibility] = useState<MRT_VisibilityState>(
    () => activeTemplate?.settings.columnVisibility || {}
  );
  const [columnOrder, setColumnOrder] = useState<MRT_ColumnOrderState>(
    () => activeTemplate?.settings.columnOrder || []
  );
  const [density, setDensity] = useState<MRT_DensityState>(
    () => activeTemplate?.settings.density || 'xs'
  );
  const [columnFilters, setColumnFilters] = useState<MRT_ColumnFiltersState>(
    () => activeTemplate?.settings.columnFilters || []
  );
  const prevColumnFiltersRef = useRef<MRT_ColumnFiltersState>(
    activeTemplate?.settings.columnFilters || []
  );
  const syncingFromFiltersRef = useRef(false);
  const syncingFromTemplateRef = useRef(false);
  const urlFiltersAppliedRef = useRef(false);
  const [newTemplateName, setNewTemplateName] = useState('');
  const [renameValue, setRenameValue] = useState(activeTemplate?.name || '');

  // Alliance autocomplete
  const [allianceQuery, setAllianceQuery] = useState(activeFilters.alliance || '');
  const [debouncedAllianceQuery] = useDebouncedValue(allianceQuery, 300);
  const { data: allianceOptions = [] } = useQuery({
    queryKey: ['alliance-search', token, debouncedAllianceQuery],
    queryFn: () => debouncedAllianceQuery.length >= 2 && token ? searchAlliances(token, debouncedAllianceQuery, 15) : Promise.resolve([]),
    enabled: !!token && debouncedAllianceQuery.length >= 2,
  });

  // Fetch raids data - must be before any conditional returns
  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['raids', token, appliedNationId],
    queryFn: () => {
      const filters: any = { minScore: 15, vmode: false };
      if (appliedNationId) {
        filters.attackerNationId = parseInt(appliedNationId, 10);
      }
      return fetchRaids(token || '', filters);
    },
    retry: false,
    enabled: !!token,
  });

  // Auto-fill score when attacker data loads and we have a nation ID
  useEffect(() => {
    if (data?.attacker?.score && appliedNationId) {
      setDraftFilters(prev => ({ 
        ...prev, 
        yourScore: data.attacker.score!.toString(),
        scoreMode: 'yours'
      }));
    } else if (!appliedNationId && draftFilters.scoreMode === 'yours') {
      // Reset to custom if nation ID is cleared
      setDraftFilters(prev => ({ ...prev, scoreMode: 'custom' }));
    }
  }, [data?.attacker?.score, appliedNationId]);

  // Sync draftNationId with savedNationId when it changes
  useEffect(() => {
    if (savedNationId && !appliedNationId) {
      setAppliedNationId(savedNationId);
      setDraftNationId(savedNationId);
    }
  }, [savedNationId, appliedNationId]);

  useEffect(() => {
    if (!activeTemplate) return;
    const cloned = cloneSettings(activeTemplate.settings);
    syncingFromTemplateRef.current = true;
    setColumnVisibility(cloned.columnVisibility);
    setColumnOrder(cloned.columnOrder);
    setDensity(cloned.density);
    setColumnFilters(cloned.columnFilters);
    setRenameValue(activeTemplate.name);
  }, [activeTemplate]);

  useEffect(() => {
    persistCustomTemplates(templates.filter((t) => !t.builtIn));
  }, [templates]);

  useEffect(() => {
    try {
      localStorage.setItem(ACTIVE_TEMPLATE_STORAGE_KEY, activeTemplateId);
    } catch (error) {
      console.warn('Failed to persist active template id', error);
    }
  }, [activeTemplateId]);

  useEffect(() => {
    if (!activeTemplate || activeTemplate.builtIn) return;
    setTemplates((prev) => {
      let changed = false;
      const next = prev.map((t) => {
        if (t.id !== activeTemplateId) return t;
        const nextSettings: TableTemplateSettings = {
          columnVisibility,
          columnOrder,
          density,
          columnFilters,
        };
        if (areSettingsEqual(t.settings, nextSettings)) return t;
        changed = true;
        return { ...t, settings: cloneSettings(nextSettings) };
      });
      return changed ? next : prev;
    });
  }, [columnVisibility, columnOrder, density, columnFilters, activeTemplate, activeTemplateId]);

  useEffect(() => {
    if (urlFiltersAppliedRef.current || !initialColumnFilters.length) return;
    urlFiltersAppliedRef.current = true;
    syncingFromFiltersRef.current = true;
    setColumnFilters((prev) => mergeColumnFilters(prev, initialColumnFilters));
  }, [initialColumnFilters]);

  useEffect(() => {
    prevColumnFiltersRef.current = columnFilters;
  }, [columnFilters]);

  // Apply filters locally in the browser - must be before conditional returns
  const filteredTargets = useMemo(() => {
    if (!data?.targets) return [];
    
    let filtered = [...data.targets];

    // Alliance filter
    if (activeFilters.alliance) {
      const query = activeFilters.alliance.toLowerCase();
      filtered = filtered.filter(nation => 
        nation.allianceName.toLowerCase().includes(query)
      );
    }

    // Beige filter
    if (activeFilters.beige === true) {
      filtered = filtered.filter(nation => nation.beigeTurns > 0);
    } else if (activeFilters.beige === false) {
      filtered = filtered.filter(nation => nation.beigeTurns <= 0);
    }

    // Max wars filter (using defSlots as defensive wars)
    if (activeFilters.maxWars !== undefined) {
      filtered = filtered.filter(nation => (3 - nation.defSlots) <= activeFilters.maxWars!);
    }

    // Inactivity filter
    if (activeFilters.inactiveMinDays !== undefined) {
      filtered = filtered.filter(nation => nation.daysInactive >= activeFilters.inactiveMinDays!);
    }

    // Scope filter
    if (activeFilters.scope === 'apps_or_none') {
      filtered = filtered.filter(nation => 
        nation.alliancePosition === 'NOALLIANCE' || nation.alliancePosition === 'APPLICANT'
      );
    } else if (activeFilters.scope === 'no_alliance') {
      filtered = filtered.filter(nation => nation.allianceId === '0');
    }

    // Min beige loot filter (using nationLoot)
    if (activeFilters.minBeigeLoot !== undefined && activeFilters.minBeigeLoot > 0) {
      filtered = filtered.filter(nation => {
        const loot = parseFloat(nation.nationLoot.replace(/[^0-9.-]/g, ''));
        return loot >= activeFilters.minBeigeLoot!;
      });
    }

    // Score filter (calculate from cities - rough approximation)
    if (activeFilters.minScore !== undefined || activeFilters.maxScore !== undefined) {
      filtered = filtered.filter(nation => {
        const approxScore = nation.numCities * 150; // Rough estimate
        if (activeFilters.minScore !== undefined && approxScore < activeFilters.minScore) {
          return false;
        }
        if (activeFilters.maxScore !== undefined && approxScore > activeFilters.maxScore) {
          return false;
        }
        return true;
      });
    }

    // Performance filter
    if (activeFilters.performance) {
      filtered = filtered.filter(nation => {
        const loot = parseFloat(nation.nationLoot.replace(/[^0-9.-]/g, ''));
        return nation.monetaryNetIncome > 0 && loot > 0;
      });
    }

    return filtered;
  }, [data?.targets, activeFilters]);

  const mappedColumnFiltersFromDraft = useCallback((): MRT_ColumnFiltersState => {
    const filters: MRT_ColumnFiltersState = [];
    if (draftFilters.alliance) {
      filters.push({ id: 'allianceName', value: [draftFilters.alliance] });
    }
    if (data?.showBeige && (draftFilters.beige === 'only' || draftFilters.beige === 'hide')) {
      filters.push({ id: 'beigeTurns', value: draftFilters.beige });
    }
    if (draftFilters.maxWars !== 'all') {
      filters.push({ id: 'defSlots', value: draftFilters.maxWars });
    }
    if (draftFilters.inactiveMinDays !== 'none') {
      filters.push({ id: 'daysInactive', value: draftFilters.inactiveMinDays });
    }
    if (draftFilters.scope === 'apps_or_none') {
      filters.push({ id: 'alliancePosition', value: ['APPLICANT', 'NOALLIANCE'] });
    } else if (draftFilters.scope === 'no_alliance') {
      filters.push({ id: 'alliancePosition', value: ['NOALLIANCE'] });
    }
    if (draftFilters.minBeigeLoot !== '0') {
      filters.push({ id: 'nationLoot', value: draftFilters.minBeigeLoot });
    }
    return filters;
  }, [draftFilters, data?.showBeige]);

  const syncColumnFiltersFromDraft = useCallback(() => {
    const mapped = mappedColumnFiltersFromDraft();
    syncingFromFiltersRef.current = true;
    setColumnFilters((prev) => {
      const preserved = prev.filter((f) => !MAPPED_COLUMN_IDS.has(f.id));
      return [...preserved, ...mapped];
    });
  }, [mappedColumnFiltersFromDraft]);

  const resetFilters = useCallback(() => {
    setDraftFilters({
      alliance: '',
      beige: 'all',
      maxWars: 'all',
      inactiveMinDays: 'none',
      scope: 'all',
      minBeigeLoot: '0',
      performance: false,
      scoreMode: 'yours',
      yourScore: '',
      minScore: '',
      maxScore: '',
    });
    setAllianceQuery('');
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      ['alliance', 'beige', 'maxWars', 'inactiveMinDays', 'scope', 'minBeigeLoot', 'performance', 'scoreMode', 'yourScore', 'minScore', 'maxScore'].forEach((k) =>
        next.delete(k)
      );
      return next;
    }, { replace: true });
    syncingFromFiltersRef.current = true;
    setColumnFilters((prev) => prev.filter((f) => !MAPPED_COLUMN_IDS.has(f.id)));
  }, [setSearchParams]);

  const applyFilters = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      
      // Clear old filter params
      ['alliance', 'beige', 'maxWars', 'inactiveMinDays', 'scope', 'minBeigeLoot', 'performance', 'scoreMode', 'yourScore', 'minScore', 'maxScore'].forEach(k => next.delete(k));
      
      // Apply new filters
      if (draftFilters.alliance) next.set('alliance', draftFilters.alliance);
      
      if (draftFilters.beige === 'only') next.set('beige', 'true');
      else if (draftFilters.beige === 'hide') next.set('beige', 'false');
      
      if (draftFilters.maxWars !== 'all') next.set('maxWars', draftFilters.maxWars);
      
      if (draftFilters.inactiveMinDays !== 'none') next.set('inactiveMinDays', draftFilters.inactiveMinDays);
      
      if (draftFilters.scope !== 'all') next.set('scope', draftFilters.scope);
      
      if (draftFilters.minBeigeLoot !== '0') next.set('minBeigeLoot', draftFilters.minBeigeLoot);
      
      if (draftFilters.performance) next.set('performance', 'true');
      
      // Score handling
      if (draftFilters.scoreMode === 'yours' && draftFilters.yourScore) {
        const score = Number(draftFilters.yourScore);
        if (!Number.isNaN(score)) {
          next.set('minScore', String(Math.round(score * 0.75)));
          next.set('maxScore', String(Math.round(score * 2.5)));
          next.set('scoreMode', 'yours');
          next.set('yourScore', draftFilters.yourScore);
        }
      } else if (draftFilters.scoreMode === 'custom') {
        if (draftFilters.minScore) next.set('minScore', draftFilters.minScore);
        if (draftFilters.maxScore) next.set('maxScore', draftFilters.maxScore);
        next.set('scoreMode', 'custom');
      }
      
      return next;
    }, { replace: true });
    syncColumnFiltersFromDraft();
  };

  type ColumnFiltersUpdater = MRT_ColumnFiltersState | ((prev: MRT_ColumnFiltersState) => MRT_ColumnFiltersState);

  const handleColumnFiltersChange = (updater: ColumnFiltersUpdater) => {
    setColumnFilters((prevFilters) => {
      const nextFilters = typeof updater === 'function' ? updater(prevFilters) : updater;
      const previousFilters = prevFilters;
      prevColumnFiltersRef.current = nextFilters;

      if (syncingFromFiltersRef.current) {
        syncingFromFiltersRef.current = false;
        return nextFilters;
      }

      if (syncingFromTemplateRef.current) {
        syncingFromTemplateRef.current = false;
      }

      const changedIds: string[] = [];
      const getVal = (filters: MRT_ColumnFiltersState, id: string) =>
        filters.find((f) => f.id === id)?.value;

      MAPPED_COLUMN_IDS.forEach((id) => {
        const before = getVal(previousFilters, id);
        const after = getVal(nextFilters, id);
        if (JSON.stringify(before) !== JSON.stringify(after)) {
          changedIds.push(id);
        }
      });

      if (changedIds.length) {
        const resetDraft: Partial<typeof draftFilters> = {};
        const paramsToClear: string[] = [];

        changedIds.forEach((id) => {
          if (id === 'allianceName') {
            resetDraft.alliance = '';
            paramsToClear.push('alliance');
            setAllianceQuery('');
          }
          if (id === 'beigeTurns') {
            resetDraft.beige = 'all';
            paramsToClear.push('beige');
          }
          if (id === 'defSlots') {
            resetDraft.maxWars = 'all';
            paramsToClear.push('maxWars');
          }
          if (id === 'daysInactive') {
            resetDraft.inactiveMinDays = 'none';
            paramsToClear.push('inactiveMinDays');
          }
          if (id === 'alliancePosition') {
            resetDraft.scope = 'all';
            paramsToClear.push('scope');
          }
          if (id === 'nationLoot') {
            resetDraft.minBeigeLoot = '0';
            paramsToClear.push('minBeigeLoot');
          }
        });

        if (Object.keys(resetDraft).length) {
          setDraftFilters((prevDraft) => ({ ...prevDraft, ...resetDraft }));
        }

        if (paramsToClear.length) {
          setSearchParams((prevParams) => {
            const nextParams = new URLSearchParams(prevParams);
            paramsToClear.forEach((key) => nextParams.delete(key));
            return nextParams;
          }, { replace: true });
        }
      }

      return nextFilters;
    });
  };

  const currentSettings = useMemo<TableTemplateSettings>(
    () => ({ columnVisibility, columnOrder, density, columnFilters }),
    [columnVisibility, columnOrder, density, columnFilters]
  );

  const addCustomTemplate = useCallback(
    (name: string, settings: TableTemplateSettings) => {
      const id = `custom-${Date.now()}`;
      const newTemplate: TableTemplate = {
        id,
        name: name.trim() || 'Custom Template',
        builtIn: false,
        settings: cloneSettings(settings),
      };
      setTemplates((prev) => {
        const withoutDuplicate = prev.filter((t) => t.id !== newTemplate.id);
        return [...withoutDuplicate, newTemplate];
      });
      setActiveTemplateId(id);
    },
    []
  );

  const handleSaveTemplate = useCallback(() => {
    addCustomTemplate(newTemplateName || 'Custom Template', currentSettings);
    setNewTemplateName('');
  }, [addCustomTemplate, currentSettings, newTemplateName]);

  const handleDuplicateActive = useCallback(() => {
    if (!activeTemplate) return;
    addCustomTemplate(`${activeTemplate.name} Copy`, currentSettings);
  }, [activeTemplate, addCustomTemplate, currentSettings]);

  const handleRenameActive = useCallback(() => {
    if (!activeTemplate || activeTemplate.builtIn) return;
    const trimmed = renameValue.trim();
    if (!trimmed) return;
    setTemplates((prev) => prev.map((t) => (t.id === activeTemplateId ? { ...t, name: trimmed } : t)));
  }, [activeTemplate, activeTemplateId, renameValue]);

  const handleDeleteActive = useCallback(() => {
    if (!activeTemplate || activeTemplate.builtIn) return;
    setTemplates((prev) => {
      const next = prev.filter((t) => t.id !== activeTemplateId);
      const fallbackId = next.find((t) => t.builtIn)?.id || next[0]?.id;
      if (fallbackId) setActiveTemplateId(fallbackId);
      return next;
    });
  }, [activeTemplate, activeTemplateId]);

  // Conditional returns AFTER all hooks
  if (!token) {
    return <TokenError type="missing" />;
  }

  if (isLoading) {
    return <LoadingState message="Loading raid targets..." />;
  }

  if (error) {
    const apiError = error as unknown as ApiError;
    
    if (apiError.code === 'TOKEN_EXPIRED') {
      return <TokenError type="expired" message={apiError.message} />;
    }
    if (apiError.code === 'TOKEN_INVALID') {
      return <TokenError type="invalid" message={apiError.message} />;
    }
    
    return (
      <ErrorState
        title="Failed to load raids"
        message={apiError.message || 'An unexpected error occurred'}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data) {
    return <ErrorState title="No data" message="No raid data available" />;
  }

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        {/* Nation Configuration */}
        <Paper withBorder radius="md" p="lg" style={{ position: 'relative' }}>
          <Stack gap="xs">
            <Group gap="xs">
              <Title order={3}>Your Nation</Title>
              <Badge color="blue" variant="light">Optional</Badge>
            </Group>
            <Text size="sm" c="dimmed">
              Load your nation to pull your score automatically and keep the win% + score range aligned to you.
            </Text>
          </Stack>

          <NationIdField
            label="Nation ID"
            placeholder="Nation ID or Link to Nation"
            description="Used for win% calculations"
            size="sm"
            value={draftNationId || ''}
            onChange={setDraftNationId}
            onSubmit={() => {
              const parsed = parseNationId(draftNationId);
              if (parsed) {
                setAppliedNationId(parsed);
                setDraftNationId(parsed);
              }
            }}
            buttonLabel="Load Nation"
            buttonIcon={<IconDownload size={14} />}
            buttonDisabled={!draftNationId || draftNationId === appliedNationId}
            inputProps={{ style: { maxWidth: 260 } }}
            warningMessage={data?.warning || null}
          />
          
          {data?.attacker && appliedNationId && !isLoading && (
            <Group gap="xs" style={{ position: 'absolute', top: 16, right: 16 }}>
              <Text size="sm" c="dimmed">
                {data.attacker.nation_name}
              </Text>
              <Badge variant="light" color="blue">
                Score: {data.attacker.score?.toFixed(2) || 'N/A'}
              </Badge>
            </Group>
          )}
          {isLoading && appliedNationId && (
            <Group gap="xs" style={{ position: 'absolute', top: 16, right: 16 }}>
              <Loader size="xs" />
              <Text size="xs" c="dimmed">Loading...</Text>
            </Group>
          )}
        </Paper>

        <Paper withBorder radius="md" p="lg">
          <Stack gap="sm">
            <Stack gap={4}>
              <Group gap="xs">
                <Title order={3}>Raid Filters</Title>
              </Group>
              <Text size="sm" c="dimmed">
                Adjust the filters below to refine your raid target list.
              </Text>
            </Stack>
            <Grid gutter={{ base: 'sm', sm: 'md' }}>
              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Beige Status</Text>
                      {draftFilters.beige !== 'all' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, beige: 'all' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Choose whether to include beige nations.</Text>
                    <Select
                      size="xs"
                      data={[
                        { value: 'all', label: 'Show all nations' },
                        { value: 'only', label: 'Only beige nations' },
                        { value: 'hide', label: 'Hide beige nations' },
                      ]}
                      value={draftFilters.beige}
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, beige: val || 'all' }))}
                    />
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Alliance Name</Text>
                      {draftFilters.alliance && (
                        <Anchor size="xs" onClick={() => {
                          setAllianceQuery('');
                          setDraftFilters(prev => ({ ...prev, alliance: '' }));
                        }}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Search by name, acronym, or ID.</Text>
                    <Autocomplete
                      size="xs"
                      placeholder="Search by name, acronym, or ID..."
                      value={allianceQuery}
                      onChange={(val) => {
                        setAllianceQuery(val);
                        setDraftFilters(prev => ({ ...prev, alliance: val }));
                      }}
                      data={allianceOptions.map(a => a.label)}
                      limit={15}
                      onOptionSubmit={(val) => {
                        const match = val.match(/^(.+?)\s*\[/);
                        const allianceName = match ? match[1] : val;
                        setAllianceQuery(allianceName);
                        setDraftFilters(prev => ({ ...prev, alliance: allianceName }));
                      }}
                    />
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Alliance Membership</Text>
                      {draftFilters.scope !== 'all' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, scope: 'all' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Limit results by applicant or unaffiliated status.</Text>
                    <Select
                      size="xs"
                      data={[
                        { value: 'all', label: 'All nations' },
                        { value: 'apps_or_none', label: 'Applicants + No alliance' },
                        { value: 'no_alliance', label: 'No alliance only' },
                      ]}
                      value={draftFilters.scope}
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, scope: (val || 'all') as 'all' | 'apps_or_none' | 'no_alliance' }))}
                    />
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Defensive Wars</Text>
                      {draftFilters.maxWars !== 'all' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, maxWars: 'all' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Upper bound on current defensive wars.</Text>
                    <Group gap="xs" align="center" wrap="nowrap">
                      <Select
                        size="xs"
                        style={{ flex: 1, minWidth: 120 }}
                        data={[
                          { value: 'all', label: 'Any' },
                          { value: '0', label: '0' },
                          { value: '1', label: '≤1' },
                          { value: '2', label: '≤2' },
                        ]}
                        value={draftFilters.maxWars}
                        onChange={(val) => setDraftFilters(prev => ({ ...prev, maxWars: val || 'all' }))}
                      />
                      <Text size="sm" c="dimmed">
                        active wars
                      </Text>
                    </Group>
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Inactivity</Text>
                      {draftFilters.inactiveMinDays !== 'none' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, inactiveMinDays: 'none' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Pick a minimum days inactive window.</Text>
                    <Group gap="xs" align="center" wrap="nowrap">
                      <Select
                        size="xs"
                        style={{ flex: 1 }}
                        data={[
                          { value: 'none', label: "Not" },
                          { value: '3', label: '3+ days' },
                          { value: '5', label: '5+ days' },
                          { value: '7', label: '7+ days' },
                          { value: '14', label: '14+ days' },
                          { value: '30', label: '30+ days' },
                        ]}
                        value={draftFilters.inactiveMinDays}
                        onChange={(val) => setDraftFilters(prev => ({ ...prev, inactiveMinDays: val || 'none' }))}
                      />
                      <Text size="sm" c="dimmed">
                        inactive
                      </Text>
                    </Group>
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Min Previous Beige Loot</Text>
                      {draftFilters.minBeigeLoot !== '0' && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, minBeigeLoot: '0' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Require a minimum prior beige payout.</Text>
                    <Select
                      size="xs"
                      data={[
                        { value: '0', label: 'No minimum' },
                        { value: '5000000', label: '$5 million' },
                        { value: '10000000', label: '$10 million' },
                        { value: '20000000', label: '$20 million' },
                      ]}
                      value={draftFilters.minBeigeLoot}
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, minBeigeLoot: val || '0' }))}
                    />
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, md: 8, lg: 8 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap="xs">
                    <Group gap="xs" justify="space-between">
                      <Text size="sm" fw={600}>Score Range</Text>
                      {(draftFilters.scoreMode !== 'yours' || draftFilters.yourScore || draftFilters.minScore || draftFilters.maxScore) && (
                        <Anchor size="xs" onClick={() => setDraftFilters(prev => ({ ...prev, scoreMode: 'yours', yourScore: '', minScore: '', maxScore: '' }))}>
                          reset
                        </Anchor>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">Use your score or set custom limits.</Text>
                    <Select
                      size="xs"
                      data={[
                        { value: 'custom', label: 'Custom min/max' },
                        { value: 'yours', label: 'Based on your score (0.75x - 2.5x)', disabled: !appliedNationId },
                      ]}
                      value={draftFilters.scoreMode}
                      onChange={(val) => setDraftFilters(prev => ({ ...prev, scoreMode: val || 'custom' }))}
                    />
                    
                    {draftFilters.scoreMode === 'yours' ? (
                      <NumberInput
                        size="xs"
                        label="Your Score"
                        placeholder={appliedNationId ? "Auto-filled from nation" : "Set nation ID above"}
                        value={draftFilters.yourScore}
                        onChange={(val) => setDraftFilters(prev => ({ ...prev, yourScore: val?.toString() || '' }))}
                        min={0}
                        step={0.01}
                        disabled={!appliedNationId}
                      />
                    ) : (
                      <Grid gutter="sm">
                        <Grid.Col span={6}>
                          <NumberInput
                            size="xs"
                            label="Min Score"
                            placeholder="Min"
                            value={draftFilters.minScore}
                            onChange={(val) => setDraftFilters(prev => ({ ...prev, minScore: val?.toString() || '' }))}
                            min={0}
                            step={0.1}
                          />
                        </Grid.Col>
                        <Grid.Col span={6}>
                          <NumberInput
                            size="xs"
                            label="Max Score"
                            placeholder="Max"
                            value={draftFilters.maxScore}
                            onChange={(val) => setDraftFilters(prev => ({ ...prev, maxScore: val?.toString() || '' }))}
                            min={0}
                            step={0.1}
                          />
                        </Grid.Col>
                      </Grid>
                    )}
                  </Stack>
                </Paper>
              </Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6, md: 4, lg: 4 }}>
                <Paper withBorder radius="sm" p="sm">
                  <Stack gap={6}>
                    <Text size="sm" fw={600}>Performance Filter</Text>
                    <Text size="xs" c="dimmed">
                      Filters out "bad" targets: nations with negative income, stronger ground force than you, or $0 previous beige loot.
                    </Text>
                    <Switch
                      size="sm"
                      label="Hide low-value targets"
                      checked={draftFilters.performance}
                      onChange={(event) =>
                        setDraftFilters(prev => ({ ...prev, performance: event.currentTarget.checked }))
                      }
                    />
                  </Stack>
                </Paper>
              </Grid.Col>
            </Grid>

            <Group gap="sm" justify="center">
              <Button
                leftSection={<IconSearch size={16} />}
                onClick={applyFilters}
                size="sm"
              >
                Apply Filters
              </Button>
              <Button
                leftSection={<IconX size={16} />}
                onClick={resetFilters}
                variant="light"
                color="gray"
                size="sm"
              >
                Reset All
              </Button>
            </Group>
          </Stack>
        </Paper>

        {/* Discord Linking Alert */}
        {!data.discordLinked && (
          <Alert
            icon={<IconAlertCircle size={16} />}
            title="Discord Integration Required for Reminders"
            color="blue"
            variant="light"
          >
            <Stack gap="xs">
              <Text size="sm">
                To enable beige reminder notifications, you need to link your Discord account with Autolycus.
              </Text>
              <Group gap="xs" align="center">
                <IconBrandDiscord size={20} />
                <Text size="sm" fw={600}>
                  Run <Text span c="blue" ff="monospace">/raids</Text> in any Discord server where the Autolycus bot is present.
                </Text>
              </Group>
              <Text size="xs" c="dimmed">
                Once linked, you'll see reminder toggle buttons in the table below for beige nations.
              </Text>
            </Stack>
          </Alert>
        )}

        <Paper withBorder radius="md" p="lg">
          <Stack gap="sm">
            <Group justify="space-between" align="center">
              <Group gap="xs" align="center">
                <Title order={3}>Chef's Suggestions</Title>
                <Badge color="orange" variant="light">Table templates</Badge>
              </Group>
              {activeTemplate && (
                <Badge color={activeTemplate.builtIn ? 'gray' : 'green'} variant="filled">
                  Active: {activeTemplate.name}
                </Badge>
              )}
            </Group>
            <Text size="sm" c="dimmed">
              Swap curated layouts for the raid table. Built-ins are locked; duplicate one or save your own and changes save instantly.
            </Text>
            <Grid gutter={{ base: 'sm', sm: 'md' }}>
              <Grid.Col span={{ base: 12, md: 6 }}>
                <Stack gap="xs">
                  <Select
                    size="sm"
                    label="Active template"
                    data={templates.map((t) => ({
                      value: t.id,
                      label: `${t.name}${t.builtIn ? ' (built-in)' : ''}`,
                    }))}
                    value={activeTemplateId}
                    onChange={(val) => val && setActiveTemplateId(val)}
                  />
                  <Group gap="xs">
                    <Button
                      leftSection={<IconCopy size={16} />}
                      variant="light"
                      onClick={handleDuplicateActive}
                      size="xs"
                    >
                      Duplicate active
                    </Button>
                    <Button
                      leftSection={<IconTrash size={16} />}
                      variant="light"
                      color="red"
                      onClick={handleDeleteActive}
                      disabled={!!activeTemplate?.builtIn}
                      size="xs"
                    >
                      Delete active
                    </Button>
                  </Group>
                </Stack>
              </Grid.Col>

              <Grid.Col span={{ base: 12, md: 6 }}>
                <Stack gap="xs">
                  <Group gap="xs" align="center">
                    <TextInput
                      label="New template name"
                      placeholder="e.g. Ground Sweep"
                      size="sm"
                      value={newTemplateName}
                      onChange={(e) => setNewTemplateName(e.currentTarget.value)}
                      style={{ flex: 1 }}
                    />
                    <Button
                      leftSection={<IconPlus size={16} />}
                      size="xs"
                      onClick={handleSaveTemplate}
                    >
                      Save current as new
                    </Button>
                  </Group>
                  <Group gap="xs" align="center">
                    <TextInput
                      label="Rename active"
                      placeholder="Custom name"
                      size="sm"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.currentTarget.value)}
                      disabled={!!activeTemplate?.builtIn}
                      style={{ flex: 1 }}
                    />
                    <Button
                      leftSection={<IconPencil size={16} />}
                      size="xs"
                      onClick={handleRenameActive}
                      disabled={!!activeTemplate?.builtIn}
                    >
                      Rename
                    </Button>
                  </Group>
                </Stack>
              </Grid.Col>
            </Grid>
            <Group gap="xs" wrap="wrap">
              {templates.map((t) => (
                <Badge
                  key={t.id}
                  color={t.id === activeTemplateId ? 'green' : 'gray'}
                  variant={t.id === activeTemplateId ? 'filled' : 'light'}
                >
                  {t.name}{t.builtIn ? ' • locked' : ''}
                </Badge>
              ))}
            </Group>
            <Divider />
            <Text size="xs" c="dimmed">
              Custom templates live in your browser storage (keys: {TEMPLATE_STORAGE_KEY} for data, {ACTIVE_TEMPLATE_STORAGE_KEY} for the active choice).
            </Text>
          </Stack>
        </Paper>

        {/* Header */}
        <Stack gap="xs">
          <Title order={2}>Raid Targets</Title>
          <Text c="dimmed">
            Find profitable targets to raid. Click column headers to sort,
            use filters to narrow down results.
          </Text>
        </Stack>

        {/* Table */}
        <RaidsTable
          data={filteredTargets}
          token={token}
          showBeige={data.showBeige}
          discordLinked={data.discordLinked}
          initialSorting={initialSorting}
          columnVisibility={columnVisibility}
          columnOrder={columnOrder}
          density={density}
          columnFilters={columnFilters}
          onColumnVisibilityChange={setColumnVisibility}
          onColumnOrderChange={setColumnOrder}
          onDensityChange={setDensity}
          onColumnFiltersChange={handleColumnFiltersChange}
        />
      </Stack>
    </Container>
  );
}
