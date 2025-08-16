import React, { useState, useEffect } from 'react'
import './App.css'
import { metaAPI } from './api/meta'
import { runsAPI } from './api/runs'
import type { Platform, Profile, SKU } from './api/meta'
import type { RunConfig } from './api/runs'

interface ProfileCombination {
  id: string
  userType: 'guest' | 'member'
  location: 'kr' | 'us'
  device: 'pc' | 'mobile'
  displayName: string
}

function App() {
  const [platforms, setPlatforms] = useState<Platform[]>([])
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [selectedPlatform, setSelectedPlatform] = useState<string>('')
  const [selectedSKUs, setSelectedSKUs] = useState<Array<{url: string, name: string}>>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string>('')
  const [isRunning, setIsRunning] = useState<boolean>(false)


  // Profile combination settings
  const [currentProfile, setCurrentProfile] = useState({
    userType: 'guest' as 'guest' | 'member',
    location: 'kr' as 'kr' | 'us',
    device: 'pc' as 'pc' | 'mobile'
  })
  const [savedProfiles, setSavedProfiles] = useState<ProfileCombination[]>([])

  // New SKU input
  const [newSkuUrl, setNewSkuUrl] = useState<string>('')
  const [newSkuName, setNewSkuName] = useState<string>('')

  // New Platform URL input
  const [newPlatformUrl, setNewPlatformUrl] = useState<string>('')
  const [platformUrls, setPlatformUrls] = useState<string[]>([])

  // Initial data load
  useEffect(() => {
    loadInitialData()
  }, [])

  const loadInitialData = async () => {
    try {
      const [platformsData, profilesData] = await Promise.all([
        metaAPI.getPlatforms(),
        metaAPI.getProfiles()
      ])
      setPlatforms(platformsData)
      setProfiles(profilesData)
      setLoading(false)
    } catch (err) {
      console.error('❌ 초기 데이터 로딩 실패:', err);
      const errorMessage = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
      setError(`데이터 로딩 중 오류가 발생했습니다: ${errorMessage}`);
      setLoading(false)
    }
  }

  const refreshAPIData = async () => {
    try {
      setError('');
      
      // API 데이터만 새로 가져오기 (사용자 설정은 유지)
      const [platformsData, profilesData] = await Promise.all([
        metaAPI.getPlatforms(),
        metaAPI.getProfiles()
      ])
      
      setPlatforms(platformsData)
      setProfiles(profilesData)
      
      console.log('✅ API 데이터 새로고침 완료');
    } catch (err) {
      console.error('❌ API 데이터 새로고침 실패:', err);
      const errorMessage = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
      setError(`데이터 새로고침 실패: ${errorMessage}`);
    }
  }

  const generateProfileId = (userType: string, location: string, device: string) => {
    return `${userType}_${location}_${device}_${Date.now()}`
  }

  const generateDisplayName = (userType: string, location: string, device: string) => {
    const userTypeText = userType === 'guest' ? 'Guest' : 'Member'
    const locationText = location === 'kr' ? 'KR' : 'US'
    const deviceText = device === 'pc' ? 'PC' : 'Mobile'
    return `${userTypeText} ${locationText} ${deviceText}`
  }

  const addProfileCombination = () => {
    // 중복 체크: 같은 조합의 프로필이 이미 존재하는지 확인
    const isDuplicate = savedProfiles.some(profile => 
      profile.userType === currentProfile.userType &&
      profile.location === currentProfile.location &&
      profile.device === currentProfile.device
    );

    if (isDuplicate) {
      alert('이미 동일한 프로필 조합이 존재합니다.');
      return;
    }

    const newProfile: ProfileCombination = {
      id: generateProfileId(currentProfile.userType, currentProfile.location, currentProfile.device),
      userType: currentProfile.userType,
      location: currentProfile.location,
      device: currentProfile.device,
      displayName: generateDisplayName(currentProfile.userType, currentProfile.location, currentProfile.device)
    }
    setSavedProfiles(prev => [...prev, newProfile])
  }

  const removeProfileCombination = (profileId: string) => {
    setSavedProfiles(prev => prev.filter(profile => profile.id !== profileId))
  }

  const handleAddSku = () => {
    if (newSkuUrl.trim() && newSkuName.trim() && !selectedSKUs.some(sku => sku.url === newSkuUrl.trim())) {
      setSelectedSKUs(prev => [...prev, { url: newSkuUrl.trim(), name: newSkuName.trim() }]);
      setNewSkuUrl('');
      setNewSkuName('');
    } else if (!newSkuUrl.trim()) {
      alert('상품 URL을 입력해주세요.');
    } else if (!newSkuName.trim()) {
      alert('상품명을 입력해주세요.');
    } else if (selectedSKUs.some(sku => sku.url === newSkuUrl.trim())) {
      alert('이미 등록된 상품 URL입니다.');
    } else {
      alert('유효한 상품 정보를 입력해주세요.');
    }
  };

  const handleRemoveSku = (index: number) => {
    setSelectedSKUs(prev => prev.filter((_, i) => i !== index));
  };

  const handleAddPlatformUrl = () => {
    const trimmedUrl = newPlatformUrl.trim();
    
    if (!trimmedUrl) {
      alert('플랫폼 URL을 입력해주세요.');
      return;
    }
    
    if (platformUrls.includes(trimmedUrl)) {
      alert('이미 등록된 플랫폼 URL입니다.');
      return;
    }
    
    // URL 추가
    const newUrls = [...platformUrls, trimmedUrl];
    setPlatformUrls(newUrls);
    setNewPlatformUrl('');
  };

  const handleRemovePlatformUrl = (index: number) => {
    setPlatformUrls(prev => prev.filter((_, i) => i !== index));
  };

  const handleStartCrawling = async () => {
    console.log('🚀 크롤링 시작 시도...');
    console.log('선택된 플랫폼:', selectedPlatform);
    console.log('선택된 SKUs:', selectedSKUs);
    console.log('저장된 프로필:', savedProfiles);

    if (!selectedPlatform || selectedSKUs.length === 0 || savedProfiles.length === 0) {
      const errorMsg = `필수 항목이 선택되지 않았습니다:
        - 플랫폼: ${selectedPlatform || '미선택'}
        - 상품: ${selectedSKUs.length}개
        - 프로필: ${savedProfiles.length}개`;
      alert(errorMsg);
      return;
    }

    setIsRunning(true);
    setError('');
    
    try {
      const runConfig: RunConfig = {
        platforms: [selectedPlatform],
        profiles: savedProfiles.map(p => p.id),
        skus: selectedSKUs
      }
      
      console.log('📋 크롤링 설정:', runConfig);
      
      const result = await runsAPI.createRun(runConfig);
      console.log('✅ Run 생성 성공:', result);
      
      // 실제 크롤링 시작
      const startResult = await runsAPI.startRun(result.run_id);
      console.log('▶️ 크롤링 시작 성공:', startResult);
      
      alert(`크롤링이 시작되었습니다!
        - 플랫폼: ${selectedPlatform}
        - 프로필: ${savedProfiles.length}개
        - 상품: ${selectedSKUs.length}개
        - Run ID: ${result.run_id}`);
      
    } catch (err) {
      console.error('❌ 크롤링 시작 실패:', err);
      const errorMessage = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
      setError(`크롤링 시작 실패: ${errorMessage}`);
      alert(`크롤링 시작에 실패했습니다: ${errorMessage}`);
    } finally {
      setIsRunning(false);
    }
  }

  const handleRefreshData = async () => {
    console.log('🔄 데이터 새로고침 시도...');
    setError('');
    setLoading(true);
    
    try {
      // 사용자 설정 초기화
      setSelectedPlatform('');
      setSelectedSKUs([]);
      setSavedProfiles([]);
      setCurrentProfile({
        userType: 'guest',
        location: 'kr',
        device: 'pc'
      });
      setNewSkuUrl(''); // 상품 URL 입력칸 초기화
      setNewSkuName(''); // 상품명 입력칸 초기화
      setNewPlatformUrl(''); // 플랫폼 URL 입력칸 초기화
      setPlatformUrls([]); // 플랫폼 URL 목록 초기화
      
      // API 데이터 새로 로드
      await loadInitialData();
      console.log('✅ 데이터 새로고침 성공 - 모든 설정이 초기화되었습니다');
    } catch (err) {
      console.error('❌ 데이터 새로고침 실패:', err);
      const errorMessage = err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
      setError(`데이터 새로고침 실패: ${errorMessage}`);
    } finally {
      setLoading(false);
    }
  }



  if (loading) {
    return (
      <div className="App">
        <div className="loading">데이터를 로딩 중입니다...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="App">
        <div className="error">오류: {error}</div>
        <button onClick={loadInitialData}>다시 시도</button>
      </div>
    )
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>PriceWatch Dashboard</h1>
        <p>AI 기반 실시간 가격 차별 탐지 시스템</p>
        <div className="api-status">
          Flask API 연결됨 | 플랫폼: {platforms.length}개 | 프로필: {profiles.length}개
        </div>
      </header>
      <main className="main-content">
        <div className="control-panel">
          <h2>환경 제어 패널</h2>
          <div className="panel-grid">
            <div className="panel-card">
              <h3>플랫폼 선택</h3>
              <select
                value={selectedPlatform}
                onChange={(e) => setSelectedPlatform(e.target.value)}
                className="platform-select"
              >
                <option value="">플랫폼을 선택하세요</option>
                {platforms.map(platform => (
                  <option key={platform.id} value={platform.id}>
                    {platform.name}
                  </option>
                ))}
              </select>
              
              <div className="platform-url-section">
                <h4 className="platform-url-title">직접 입력</h4>
                <div className="platform-url-input-group">
                  <input
                    type="text"
                    placeholder="플랫폼 URL을 입력하세요"
                    className="platform-url-input"
                    value={newPlatformUrl}
                    onChange={(e) => setNewPlatformUrl(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleAddPlatformUrl()}
                  />
                  <button
                    className="add-platform-url-btn"
                    onClick={handleAddPlatformUrl}
                    disabled={!newPlatformUrl.trim()}
                  >
                    추가
                  </button>
                </div>
                
                <div className="saved-platform-urls">
                  <div className="platform-url-list">
                    {platformUrls.map((url, index) => (
                      <div key={index} className="saved-platform-url-item">
                        <span>{url}</span>
                        <button
                          className="remove-btn"
                          onClick={() => handleRemovePlatformUrl(index)}
                        >
                          삭제
                        </button>
                      </div>
                    ))}
                    {platformUrls.length === 0 && (
                      <p className="no-platform-urls">등록된 플랫폼 URL이 없습니다</p>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="panel-card">
              <h3>상품</h3>
              <div className="sku-input-section">
                <div className="sku-input-group">
                  <input
                    type="text"
                    placeholder="상품 URL을 입력하세요"
                    className="sku-url-input"
                    value={newSkuUrl}
                    onChange={(e) => setNewSkuUrl(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleAddSku()}
                  />
                  <input
                    type="text"
                    placeholder="상품명을 입력하세요"
                    className="sku-name-input"
                    value={newSkuName}
                    onChange={(e) => setNewSkuName(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleAddSku()}
                  />
                  <button
                    className="add-sku-btn"
                    onClick={handleAddSku}
                    disabled={!newSkuUrl.trim() || !newSkuName.trim()}
                  >
                    추가
                  </button>
                </div>
                
                <div className="saved-skus">
                  <div className="sku-list">
                    {selectedSKUs.length > 0 ? (
                      selectedSKUs.map((sku, index) => (
                        <div key={index} className="saved-sku-item">
                          <span>{sku.name}</span>
                          <button
                            className="remove-btn"
                            onClick={() => handleRemoveSku(index)}
                          >
                            삭제
                          </button>
                        </div>
                      ))
                    ) : (
                      <p className="no-skus">등록된 상품이 없습니다</p>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="panel-card">
              <h3>프로필 설정</h3>
              <div className="profile-builder">
                <div className="profile-dropdown-group">
                  <label>사용자 타입</label>
                  <select
                    value={currentProfile.userType}
                    onChange={(e) => setCurrentProfile(prev => ({...prev, userType: e.target.value as 'guest' | 'member'}))}
                    className="profile-select"
                  >
                    <option value="guest">Guest (비회원)</option>
                    <option value="member">Member (회원)</option>
                  </select>
                </div>

                <div className="profile-dropdown-group">
                  <label>IP 위치</label>
                  <select
                    value={currentProfile.location}
                    onChange={(e) => setCurrentProfile(prev => ({...prev, location: e.target.value as 'kr' | 'us'}))}
                    className="profile-select"
                  >
                    <option value="kr">Korea</option>
                    <option value="us">United States</option>
                  </select>
                </div>

                <div className="profile-dropdown-group">
                  <label>디바이스</label>
                  <select
                    value={currentProfile.device}
                    onChange={(e) => setCurrentProfile(prev => ({...prev, device: e.target.value as 'pc' | 'mobile'}))}
                    className="profile-select"
                  >
                    <option value="pc">PC</option>
                    <option value="mobile">Mobile</option>
                  </select>
                </div>

                <button
                  className="add-profile-btn"
                  onClick={addProfileCombination}
                >
                  프로필 추가
                </button>
              </div>

              <div className="saved-profiles">
                <h4>저장된 프로필 ({savedProfiles.length}개):</h4>
                <div className="profile-list">
                  {savedProfiles.map(profile => (
                    <div key={profile.id} className="saved-profile-item">
                      <span>{profile.displayName}</span>
                      <button
                        className="remove-btn"
                        onClick={() => removeProfileCombination(profile.id)}
                      >
                        삭제
                      </button>
                    </div>
                  ))}
                  {savedProfiles.length === 0 && (
                    <p className="no-profiles">프로필 조합을 추가해주세요</p>
                  )}
                </div>
              </div>
            </div>

            <div className="panel-card">
              <h3>실행 상태</h3>
              <div className="status-indicator">
                {isRunning ? (
                  <div className="running">실행 중...</div>
                ) : (
                  <div className="ready">준비 완료</div>
                )}
              </div>
              <div className="selection-summary">
                <div>플랫폼: {platformUrls.length > 0 ? platformUrls.join(', ') : (selectedPlatform || '미선택')}</div>
                <div>프로필: {savedProfiles.length}개</div>
                <div>상품: {selectedSKUs.length}개</div>
              </div>
              <button 
                className="config-btn" 
                onClick={handleRefreshData}
                disabled={loading}
              >
                {loading ? '새로고침 중...' : '데이터 새로고침'}
              </button>
            </div>

            <div className="panel-card">
              <h3>실험 스케줄러</h3>
              <button 
                className="scheduler-btn"
                disabled={(!selectedPlatform && platformUrls.length === 0) || selectedSKUs.length === 0 || savedProfiles.length === 0}
              >
                스케줄러 실행 &gt;
              </button>
            </div>
          </div>
        </div>

        <div className="action-buttons">
        </div>
      </main>
    </div>
  )
}

export default App 