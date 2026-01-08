/**
 * Damage Page
 *
 * Displays damage calculator with charts and tables (public page, no authentication required).
 */

import { Container, Title, Text, Stack, Group, Badge, Alert, Paper, TextInput, Button, Skeleton, SimpleGrid } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { IconClock, IconAlertCircle, IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

import { fetchDamage } from '@/api';
import { DamageDashboard } from '@/components/damage';
import { TokenError, LoadingState, ErrorState } from '@/components/common';
import type { ApiError } from '@/types';

export function DamagePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const nation1 = params.get('nation1');
  const nation2 = params.get('nation2');
  const [inputNation1, setInputNation1] = useState('');
  const [inputNation2, setInputNation2] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputNation1.trim() && inputNation2.trim()) {
      navigate(`/damage?nation1=${inputNation1.trim()}&nation2=${inputNation2.trim()}`);
    }
  };

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['damage', nation1, nation2],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('nation1', nation1!);
      params.set('nation2', nation2!);
      
      const response = await fetch(`http://localhost:5000/api/damage/?${params}`);
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to fetch damage data');
      }
      return response.json();
    },
    retry: false,
    enabled: !!nation1 && !!nation2, // Only run query if both nations exist
  });

  // Show input form and skeleton layout when no nation params
  if (!nation1 || !nation2) {
    return (
      <Container size="xl" py="xl">
        <Stack gap="lg">
          <Title order={1}>Damage Calculator</Title>
          
          <Paper p="md" withBorder>
            <form onSubmit={handleSubmit}>
              <Stack gap="md">
                <Text size="sm" c="dimmed">
                  Enter two nation IDs to calculate damage potential
                </Text>
                <Group grow>
                  <TextInput
                    placeholder="Nation 1 ID"
                    value={inputNation1}
                    onChange={(e) => setInputNation1(e.currentTarget.value)}
                    leftSection={<IconSearch size={16} />}
                  />
                  <TextInput
                    placeholder="Nation 2 ID"
                    value={inputNation2}
                    onChange={(e) => setInputNation2(e.currentTarget.value)}
                    leftSection={<IconSearch size={16} />}
                  />
                  <Button type="submit" disabled={!inputNation1.trim() || !inputNation2.trim()}>
                    Calculate Damage
                  </Button>
                </Group>
              </Stack>
            </form>
          </Paper>

          <Stack gap="md">
            <Title order={2}>Damage Analysis</Title>
            <Text c="dimmed">Enter nation IDs above to see damage calculations</Text>
            
            {/* Skeleton loaders showing expected layout */}
            <Skeleton height={300} radius="md" />
            <SimpleGrid cols={2}>
              <Skeleton height={400} radius="md" />
              <Skeleton height={400} radius="md" />
            </SimpleGrid>
          </Stack>
        </Stack>
      </Container>
    );
  }

  if (isLoading) {
    return <LoadingState message="Loading damage analysis..." />;
  }

  if (error) {
    const apiError = error as ApiError;
    
    if (apiError.code === 'TOKEN_EXPIRED') {
      return <TokenError type="expired" message={apiError.message} />;
    }
    if (apiError.code === 'TOKEN_INVALID') {
      return <TokenError type="invalid" message={apiError.message} />;
    }
    
    return (
      <ErrorState
        title="Failed to load damage data"
        message={apiError.message || 'An unexpected error occurred'}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data) {
    return <ErrorState title="No data" message="No damage data available" />;
  }

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        {/* Header */}
        <Group justify="space-between" align="flex-start">
          <Stack gap="xs">
            <Title order={2}>Damage Calculator</Title>
            <Text c="dimmed">
              Analyze war damage between two nations. Use this to plan attacks
              and maximize efficiency.
            </Text>
          </Stack>
          <Badge
            leftSection={<IconClock size={12} />}
            variant="light"
            color="gray"
          >
            Generated: {new Date(data.generatedAt).toLocaleString()}
          </Badge>
        </Group>

        {/* Dashboard */}
        <DamageDashboard data={data} />
      </Stack>
    </Container>
  );
}
