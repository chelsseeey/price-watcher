import apiClient from './client';

// 타입 정의
export interface RunConfig {
  platforms: string[];
  profiles: string[];
  skus: Array<{url: string, name: string}>;
}

export interface Run {
  id: string;
  platforms: string[];
  profiles: string[];
  skus: Array<{url: string, name: string}>;
  status: 'created' | 'running' | 'completed' | 'stopped' | 'failed';
  created_at: string;
  started_at?: string;
  stopped_at?: string;
  progress: number;
}

// API 함수들
export const runsAPI = {
  // 크롤링 실행 생성
  async createRun(config: RunConfig): Promise<{ run_id: string; status: string }> {
    const response = await apiClient.post('/api/runs', config);
    return response.data;
  },

  // 크롤링 실행 시작
  async startRun(runId: string): Promise<{ status: string }> {
    const response = await apiClient.post(`/api/runs/${runId}/start`);
    return response.data;
  },

  // 크롤링 실행 중지
  async stopRun(runId: string): Promise<{ status: string }> {
    const response = await apiClient.post(`/api/runs/${runId}/stop`);
    return response.data;
  },

  // 크롤링 실행 상태 조회
  async getRun(runId: string): Promise<Run> {
    const response = await apiClient.get(`/api/runs/${runId}`);
    return response.data;
  },

  // 크롤링 실행 목록 조회
  async listRuns(): Promise<Run[]> {
    const response = await apiClient.get('/api/runs');
    return response.data;
  },
};

export default runsAPI;
