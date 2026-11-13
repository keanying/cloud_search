<script setup lang="ts">
import type {
  ArtifactPart as ArtifactPartT,
  ClarificationPart as ClarificationPartT,
  ErrorPart as ErrorPartT,
  HighlightsPart as HighlightsPartT,
  SuggestionsPart as SuggestionsPartT,
  MessagePart,
  PlanSummaryPart as PlanSummaryPartT,
  ProgressPart as ProgressPartT,
  SourcePart as SourcePartT,
  TakeoverPart as TakeoverPartT,
  TextPart as TextPartT,
} from '@/api/types'
import TextPart from './TextPart.vue'
import ClarificationPart from './ClarificationPart.vue'
import PlanSummaryPart from './PlanSummaryPart.vue'
import ProgressPart from './ProgressPart.vue'
import SourcePart from './SourcePart.vue'
import ArtifactPart from './ArtifactPart.vue'
import ErrorPart from './ErrorPart.vue'
import TakeoverPart from './TakeoverPart.vue'
import HighlightsPart from './HighlightsPart.vue'
import SuggestionsPart from './SuggestionsPart.vue'

defineProps<{ part: MessagePart; taskId?: string | null; streaming?: boolean }>()
</script>

<template>
  <TextPart v-if="part.type === 'text'" :part="part as TextPartT" :task-id="taskId" :streaming="streaming" />
  <ClarificationPart v-else-if="part.type === 'clarification'" :part="part as ClarificationPartT" />
  <PlanSummaryPart v-else-if="part.type === 'plan_summary'" :part="part as PlanSummaryPartT" />
  <ProgressPart v-else-if="part.type === 'progress'" :part="part as ProgressPartT" />
  <SourcePart v-else-if="part.type === 'source'" :part="part as SourcePartT" />
  <ArtifactPart v-else-if="part.type === 'artifact'" :part="part as ArtifactPartT" />
  <ErrorPart v-else-if="part.type === 'error'" :part="part as ErrorPartT" />
  <TakeoverPart v-else-if="part.type === 'takeover'" :part="part as TakeoverPartT" />
  <HighlightsPart v-else-if="part.type === 'highlights'" :part="part as HighlightsPartT" :task-id="taskId" />
  <SuggestionsPart v-else-if="part.type === 'suggestions'" :part="part as SuggestionsPartT" />
</template>
