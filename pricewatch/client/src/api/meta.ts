import apiClient from './client';

// 타입 정의
export interface Platform {
  id: string;
  name: string;
  enabled: boolean;
}

export interface Profile {
  id: string;
  name: string;
}

export interface SKU {
  id: string;
  name: string;
}

// API 함수들
export const metaAPI = {
  // 플랫폼 목록 조회
  async getPlatforms(): Promise<Platform[]> {
    const response = await apiClient.get('/api/platforms');
    return response.data;
  },

  // 프로필 목록 조회
  async getProfiles(): Promise<Profile[]> {
    const response = await apiClient.get('/api/profiles');
    return response.data;
  },

  // 플랫폼별 SKU 목록 조회
  async getSKUs(platform: string): Promise<SKU[]> {
    const response = await apiClient.get(`/api/skus/${platform}`);
    return response.data;
  },
};

export default metaAPI;
