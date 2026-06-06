// CreateReport.jsx — 3-step wizard (ported from UI_GEN)
import React from 'react';
import { Btn, Card, FieldLabel, TextInput, SelectDropdown, InfoStrip, ChecklistItem, CalSans, LoadingSpinner } from './Components.jsx';
import { apiFetch } from './api.js';

const GEN_STEPS = ['Initializing', 'Querying DB', 'Processing Images', 'Generating Slides', 'Done'];

function StepIndicator({ current }) {
  const steps = ['Select', 'Verify', 'Generate'];
  return (
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 40 }}>
      {steps.map((s, i) => {
        const n = i + 1;
        const done = n < current, active = n === current;
        return (
          <React.Fragment key={s}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 12, fontWeight: 700,
                background: (done || active) ? '#242424' : '#fff',
                color: (done || active) ? '#fff' : '#898989',
                boxShadow: (done || active) ? 'none' : 'rgba(34,42,53,0.15) 0px 0px 0px 1.5px',
              }}>{done ? '✓' : n}</div>
              <span style={{ fontSize: 11, color: active ? '#242424' : '#898989', fontWeight: active ? 600 : 400 }}>{n} {s}</span>
            </div>
            {i < 2 && <div style={{ flex: 1, height: 1.5, background: n < current ? '#242424' : 'rgba(34,42,53,0.12)', margin: '0 8px', marginBottom: 18 }} />}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function Step1({ onNext, prList, prLoading }) {
  const [pr, setPr] = React.useState('');
  const [tp, setTp] = React.useState('');
  const [timepoints, setTimepoints] = React.useState([]);
  const [tpLoading, setTpLoading] = React.useState(false);
  const [liveRevision, setLiveRevision] = React.useState('');
  const [lot, setLot] = React.useState('');
  const [lots, setLots] = React.useState([]);
  const [lotError, setLotError] = React.useState('');
  const [prData, setPrData] = React.useState(null);

  const handlePrChange = async (val) => {
    setPr(val);
    setTp('');
    setLot('');
    setTpLoading(true);
    try {
      const res = await apiFetch(`/api/product-request/${val}`);
      if (res.ok) setPrData(await res.json());

      const tpRes = await apiFetch(`/api/product-request/${val}/timepoints`);
      if (tpRes.ok) setTimepoints(await tpRes.json());

      const lotRes = await apiFetch(`/api/product-request/${val}/lots`);
      if (lotRes.ok) {
        const lotList = await lotRes.json();
        setLots(lotList);
        if (lotList.length === 1) setLot(lotList[0]);
      }
    } catch (_) {
    } finally {
      setTpLoading(false);
    }
  };

  const handleTpChange = async (val) => {
    setTp(val);
    if (val && pr) {
      try {
        const res = await apiFetch(`/api/product-request/${pr}/${val}/next-revision`);
        if (res.ok) {
          const data = await res.json();
          setLiveRevision(data.nextRevision);
        }
      } catch (_) {}
    }
  };

  const validateLot = v => {
    setLot(v);
    setLotError(v && !/^[A-Z]{5}\d{4}\.\d$/.test(v) && lots.length === 0 ? 'Invalid format — expected e.g. MTDQS0906.1' : '');
  };

  return (
    <Card>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div>
          <FieldLabel>Product Request No.</FieldLabel>
          <SelectDropdown
            options={prList}
            value={pr}
            onChange={handlePrChange}
            loading={prLoading}
            placeholder="Select PR No. (e.g. PR2024001)"
          />
        </div>
        
        <div>
          <FieldLabel>Lot No.</FieldLabel>
          {lots.length > 1 ? (
            <SelectDropdown
              options={lots.map(l => ({ value: l, label: l }))}
              value={lot}
              onChange={setLot}
              placeholder="Select Lot No."
            />
          ) : lots.length === 1 ? (
            <div style={{ padding: '10px 14px', background: '#f9f9f9', borderRadius: 8, fontSize: 14, fontWeight: 600, color: '#242424', border: '1px solid #eee' }}>
              {lot}
            </div>
          ) : (
            <TextInput placeholder="e.g. MTDQS0906.1" value={lot} onChange={e => validateLot(e.target.value)} error={lotError} />
          )}
        </div>

        <div>
          <FieldLabel>DPA Report</FieldLabel>
          <SelectDropdown 
            options={timepoints} 
            value={tp} 
            onChange={handleTpChange} 
            loading={tpLoading} 
            placeholder={pr ? "Select Stress test" : "Please select PR first"} 
          />
        </div>

        {pr && tp && lot && (
          <InfoStrip 
            items={[
              { label: 'Customer', value: prData.backgroundInfo?.customerName },
              { label: 'Package Type', value: prData.backgroundInfo?.packageType },
              { label: 'Device Name', value: prData.billOfMaterial?.device },
              { label: 'PR Number', value: prData.productRequestNo },
              { label: 'Request Date', value: prData.date },
              { label: 'Revision', value: liveRevision || prData.revision || 'A' },
              { label: 'Lot No.', value: lot },
              { label: 'Assembly Site', value: prData.backgroundInfo?.assemblySite }
            ]} 
          />
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: 4 }}>
          <Btn variant="primary" onClick={() => onNext({ pr, tp, lot, prData, liveRevision })} disabled={!pr || !tp || !lot || !!lotError}>Continue →</Btn>
        </div>
      </div>
    </Card>
  );
}

function SectionPreviewItem({ folder, data, selected, onToggleSelect }) {
  const [expanded, setExpanded] = React.useState(false);
  const [previewImages, setPreviewImages] = React.useState([]);
  const [previewImc, setPreviewImc] = React.useState([]);
  const [previewBond, setPreviewBond] = React.useState([]);
  const [previewSem, setPreviewSem] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [showAllImages, setShowAllImages] = React.useState(false);
  const [fullscreenImage, setFullscreenImage] = React.useState(null);

  const isSEM = folder.name.toUpperCase().includes('CROSS SECTION');

  const groupedSem = React.useMemo(() => {
    if (!previewSem || previewSem.length === 0) return {};
    return previewSem.reduce((acc, r) => {
      if (!acc[r.unitId]) acc[r.unitId] = [];
      acc[r.unitId].push(r);
      return acc;
    }, {});
  }, [previewSem]);

  const groupedBond = React.useMemo(() => {
    if (!previewBond || previewBond.length === 0) return {};
    return previewBond.reduce((acc, curr) => {
       if (!acc[curr.testType]) acc[curr.testType] = {};
       if (!acc[curr.testType][curr.unitId]) acc[curr.testType][curr.unitId] = [];
       acc[curr.testType][curr.unitId].push(curr);
       return acc;
    }, {});
  }, [previewBond]);

  const groupedImages = React.useMemo(() => {
    if (!previewImages || previewImages.length === 0) return null;
    
    const groups = {};
    const others = [];

    previewImages.forEach(img => {
      let unit, sub;
      
      // ลำดับความสำคัญ: 1. ใช้ imageSeq จาก DB ถ้ามี, 2. ถ้าไม่มีค่อยแกะจากชื่อไฟล์
      if (img.imageSeq) {
        if (img.imageSeq.includes('-')) {
          const parts = img.imageSeq.split('-');
          unit = parseInt(parts[0], 10);
          sub = parts[1];
        } else {
          unit = parseInt(img.imageSeq, 10);
          sub = '0';
        }
      } else {
        const match = img.fileName.match(/^(\d+)(?:-(\w+))?(?:_|\.)/);
        if (match) {
          unit = parseInt(match[1], 10);
          sub = match[2] || '0';
        }
      }

      if (unit !== undefined && !isNaN(unit)) {
        if (!groups[unit]) groups[unit] = {};
        groups[unit][sub] = img;
      } else {
        others.push(img);
      }
    });

    if (Object.keys(groups).length === 0) {
       return { type: 'flat', items: previewImages };
    }

    const subs = new Set();
    Object.values(groups).forEach(unitObj => {
       Object.keys(unitObj).forEach(s => subs.add(s));
    });
    const sortedSubs = Array.from(subs).sort((a,b) => {
       if (a === '0') return -1;
       if (b === '0') return 1;
       return a.localeCompare(b, undefined, {numeric: true});
    });
    const sortedUnits = Object.keys(groups).sort((a,b) => parseInt(a) - parseInt(b));

    return { type: 'grouped', groups, others, sortedSubs, sortedUnits };
  }, [previewImages]);

  const getExpected = (name) => {
    const upName = name.toUpperCase();
    if (upName.includes('EXTERNAL VISUAL')) return 56;
    if (upName.includes('X-RAY')) return 28;
    if (upName.includes('DELAM')) return 2;
    if (upName.includes('DECAP')) return 25;
    if (upName.includes('BS,WP,SP')) return 3;
    if (upName.includes('CROSS SECTION')) return 6;
    if ((upName.includes('CR') || upName.includes('C-R')) && !upName.includes('CROSS')) return 6;
    return null;
  };

  const expectedTotal = getExpected(folder.name);
  let detailText = '';

  if (folder.name.includes('BS,WP,SP')) {
    detailText = expectedTotal ? `${folder.bondCount || 0}/${expectedTotal}` : `${folder.bondCount || 0}`;
  } else if (folder.name.includes('IMC')) {
    detailText = `${folder.fileCount}/25`;
  } else if (folder.name.toUpperCase().includes('CROSS SECTION')) {
    detailText = `${folder.semCount || 0}/6`;
  } else if ((folder.name.toUpperCase().includes('CR') || folder.name.toUpperCase().includes('C-R')) && !folder.name.toUpperCase().includes('CROSS')) {
    detailText = `${folder.fileCount}/6`;
  } else {
    detailText = expectedTotal ? `${folder.fileCount}/${expectedTotal}` : `${folder.fileCount} Image`;
  }

  const handleExpand = async (e) => {
    e.stopPropagation();
    if (!expanded) {
      setLoading(true);
      try {
        const catClean = folder.name.replace(/^\d+\./, ''); // e.g. "EXTERNAL VISUAL"
        const [imgRes, imcRes, bondRes, semRes] = await Promise.all([
          !isSEM && folder.fileCount > 0 ? apiFetch(`/api/product-request/${data.pr}/${data.tp}/${encodeURIComponent(data.lot)}/preview-images?category=${encodeURIComponent(catClean)}`).then(r => r.json()) : Promise.resolve([]),
          folder.name.includes('IMC') && folder.imcCount > 0 ? apiFetch(`/api/product-request/${data.pr}/${data.tp}/${encodeURIComponent(data.lot)}/preview-imc`).then(r => r.json()) : Promise.resolve([]),
          folder.name.includes('BS,WP,SP') && folder.bondCount > 0 ? apiFetch(`/api/product-request/${data.pr}/${data.tp}/${encodeURIComponent(data.lot)}/preview-bond`).then(r => r.json()) : Promise.resolve([]),
          isSEM ? apiFetch(`/api/product-request/${data.pr}/${data.tp}/${encodeURIComponent(data.lot)}/preview-sem`).then(r => r.json()) : Promise.resolve([]),
        ]);
        setPreviewImages(imgRes);
        setPreviewImc(imcRes);
        setPreviewBond(bondRes);
        setPreviewSem(semRes);
      } finally {
        setLoading(false);
      }
    } else {
      // Reset state when collapsing
      setShowAllImages(false);
    }
    setExpanded(!expanded);
  };

  return (
    <div style={{ borderBottom: '1px solid #f5f5f5' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0', cursor: 'pointer', userSelect: 'none' }} onClick={() => onToggleSelect(folder.name)}>
        <div style={{
          width: 20, height: 20, borderRadius: 5, border: '2px solid',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0, transition: 'all 0.2s',
          background: selected ? '#242424' : 'transparent',
          borderColor: selected ? '#242424' : '#e0e0e0',
        }}>
          {selected && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#242424', fontFamily: 'Inter,sans-serif' }}>
            {folder.name.replace(/^\d+\./, '')}
          </div>
        </div>
        <div style={{ fontSize: 13, color: '#898989', fontFamily: 'Inter,sans-serif' }}>
          {detailText}
        </div>
        <button onClick={handleExpand} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#898989', padding: '4px', display: 'flex', alignItems: 'center' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>
      </div>

      {expanded && (
        <div style={{ padding: '0 0 16px 32px' }}>
          {loading ? (
             <div style={{ fontSize: 12, color: '#898989' }}>Loading preview...</div>
          ) : (
             <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {groupedImages && !folder.name.includes('BS,WP,SP') && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#898989', textTransform: 'uppercase', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                      <span>Images ({previewImages.length})</span>
                      {groupedImages.type === 'flat' && showAllImages && (
                        <span onClick={() => setShowAllImages(false)} style={{ color: '#059669', cursor: 'pointer', textTransform: 'none' }}>
                          Show Less
                        </span>
                      )}
                    </div>
                    
                    {/* Custom IMC Grid Layout (5 columns) */}
                    {folder.name.includes('IMC') ? (
                      <div style={{ 
                        display: 'grid', 
                        gridTemplateColumns: 'repeat(5, 1fr)', 
                        gap: '8px', 
                        background: '#f8fafc', 
                        padding: '10px', 
                        borderRadius: '8px',
                        border: '1px solid #e2e8f0'
                      }}>
                        {/* Loop through 5 units, each with 5 points = 25 items */}
                        {Array.from({ length: 5 }).flatMap((_, uIdx) => {
                          const unitNum = uIdx + 1;
                          return Array.from({ length: 5 }).map((_, pIdx) => {
                            const pointNum = pIdx + 1;
                            const seq = `${unitNum}-${pointNum}`;
                            const img = previewImages.find(i => {
                               // Match filename like "1-1_IMC.jpg" or similar
                               return i.fileName.startsWith(seq + '_') || i.fileName.startsWith(seq + '.');
                            });
                            const imcVal = previewImc.find(v => String(v.unitId) === seq);
                            
                            return (
                              <div key={seq} style={{ 
                                background: '#fff', 
                                border: '1px solid #cbd5e1', 
                                borderRadius: '6px', 
                                padding: '6px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '4px',
                                boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
                              }}>
                                <div style={{ fontSize: '10px', fontWeight: 'bold', color: '#64748b' }}>Point {seq}</div>
                                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                                  <div 
                                    onClick={() => img && setFullscreenImage(img)}
                                    style={{ 
                                      width: '40px', 
                                      height: '40px', 
                                      borderRadius: '4px', 
                                      background: '#f1f5f9', 
                                      overflow: 'hidden',
                                      border: '1px solid #e2e8f0',
                                      cursor: img ? 'pointer' : 'default',
                                      flexShrink: 0
                                    }}
                                  >
                                    {img ? (
                                      <img src={`/api/image?path=${encodeURIComponent(img.filePath)}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                    ) : (
                                      <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px', color: '#cbd5e1' }}>×</div>
                                    )}
                                  </div>
                                  <div style={{ 
                                    flex: 1, 
                                    height: '24px', 
                                    background: imcVal ? '#f0f9ff' : '#f8fafc', 
                                    border: '1px solid',
                                    borderColor: imcVal ? '#bae6fd' : '#e2e8f0',
                                    borderRadius: '4px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: '11px',
                                    fontWeight: 'bold',
                                    color: imcVal ? '#0369a1' : '#94a3b8'
                                  }}>
                                    {imcVal ? `${imcVal.value}%` : '-'}
                                  </div>
                                </div>
                              </div>
                            );
                          });
                        })}
                      </div>
                    ) : (
                      /* Original Table Layout for other categories */
                      groupedImages.type === 'grouped' ? (
                         <div style={{ border: '1px solid #eee', borderRadius: 8, overflow: 'hidden' }}>
                            <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'center', fontSize: 12, background: '#fff' }}>
                                 <thead style={{ position: 'sticky', top: 0, zIndex: 10, background: '#f5f5f5', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                                   <tr>
                                     <th style={{ padding: 8, borderBottom: '1px solid #ddd', borderRight: '1px solid #ddd', width: 60 }}>Unit</th>
                                     {groupedImages.sortedSubs.map((sub, i) => (
                                        <th key={sub} style={{ padding: 8, borderBottom: '1px solid #ddd', borderRight: i < groupedImages.sortedSubs.length -1 ? '1px solid #eee' : 'none' }}>
                                          {groupedImages.sortedSubs.length === 1 ? 'Image' : `Image ${i+1}`}
                                        </th>
                                     ))}
                                   </tr>
                                 </thead>
                                 <tbody>
                                   {groupedImages.sortedUnits.map(unit => {
                                     return (
                                     <tr key={unit} style={{ borderBottom: '1px solid #eee' }}>
                                       <td style={{ padding: 8, fontWeight: 'bold', borderRight: '1px solid #ddd', background: '#fafafa' }}>{unit}</td>
                                       {groupedImages.sortedSubs.map((sub, i) => {
                                          const img = groupedImages.groups[unit][sub];
                                          return (
                                            <td key={sub} style={{ padding: '8px 4px', borderRight: i < groupedImages.sortedSubs.length -1 ? '1px solid #f5f5f5' : 'none' }}>
                                              {img ? (
                                                <div 
                                                  title={img.fileName}
                                                  onClick={() => setFullscreenImage(img)}
                                                  style={{ width: 64, height: 64, margin: '0 auto', borderRadius: 6, overflow: 'hidden', cursor: 'pointer', border: '1px solid #ddd', transition: 'opacity 0.2s' }}
                                                  onMouseEnter={e => e.currentTarget.style.opacity = 0.8}
                                                  onMouseLeave={e => e.currentTarget.style.opacity = 1}
                                                >
                                                  <img src={`/api/image?path=${encodeURIComponent(img.filePath)}`} alt="preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
                                                </div>
                                              ) : (
                                                <span style={{ color: '#ccc' }}>-</span>
                                              )}
                                            </td>
                                          )
                                       })}
                                     </tr>
                                   )})}
                                 </tbody>
                              </table>
                            </div>
                            {groupedImages.others.length > 0 && (
                               <div style={{ padding: 12, display: 'flex', gap: 8, flexWrap: 'wrap', borderTop: '1px solid #eee', background: '#fafafa' }}>
                                 {groupedImages.others.map((img, i) => (
                                    <div 
                                      key={i} 
                                      title={img.fileName} 
                                      onClick={() => setFullscreenImage(img)}
                                      style={{ flexShrink: 0, width: 64, height: 64, borderRadius: 6, background: '#fff', overflow: 'hidden', border: '1px solid #ddd', cursor: 'pointer', transition: 'opacity 0.2s' }}
                                      onMouseEnter={e => e.currentTarget.style.opacity = 0.8}
                                      onMouseLeave={e => e.currentTarget.style.opacity = 1}
                                    >
                                      <img src={`/api/image?path=${encodeURIComponent(img.filePath)}`} alt="preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
                                    </div>
                                 ))}
                               </div>
                            )}
                         </div>
                      ) : (
                        <div style={{ display: 'flex', gap: 8, overflowX: showAllImages ? 'hidden' : 'auto', flexWrap: showAllImages ? 'wrap' : 'nowrap', paddingBottom: 8 }}>
                          {previewImages.slice(0, showAllImages ? undefined : 10).map((img, i) => (
                             <div 
                               key={i} 
                               title={img.fileName} 
                               onClick={() => setFullscreenImage(img)}
                               style={{ flexShrink: 0, width: 80, height: 80, borderRadius: 8, background: '#f5f5f5', overflow: 'hidden', border: '1px solid #eee', cursor: 'pointer', transition: 'opacity 0.2s' }}
                               onMouseEnter={e => e.currentTarget.style.opacity = 0.8}
                               onMouseLeave={e => e.currentTarget.style.opacity = 1}
                             >
                               <img src={`/api/image?path=${encodeURIComponent(img.filePath)}`} alt="preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
                             </div>
                          ))}
                          {!showAllImages && previewImages.length > 10 && (
                             <div 
                               onClick={() => setShowAllImages(true)}
                               style={{ width: 80, height: 80, borderRadius: 8, background: '#f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: '#898989', border: '1px solid #e0e0e0', cursor: 'pointer', flexShrink: 0, transition: 'background 0.2s' }}
                               onMouseEnter={e => e.currentTarget.style.background = '#e5e5e5'}
                               onMouseLeave={e => e.currentTarget.style.background = '#f5f5f5'}
                             >
                               +{previewImages.length - 10} more
                             </div>
                          )}
                        </div>
                      )
                    )}
                  </div>
                )}
                
                {isSEM && Object.keys(groupedSem).length > 0 && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#898989', textTransform: 'uppercase', marginBottom: 10 }}>
                      Cross Section Inspection ({previewSem.length} images)
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {Object.keys(groupedSem).sort().filter(u => u.toUpperCase() !== 'U3').map(unitId => (
                        <div key={unitId} style={{ border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
                          <div style={{ background: '#f8fafc', padding: '6px 12px', fontSize: 12, fontWeight: 700, color: '#475569', borderBottom: '1px solid #e2e8f0' }}>
                            {unitId}
                          </div>
                          <div style={{ display: 'flex', gap: 10, padding: 10, flexWrap: 'wrap' }}>
                            {groupedSem[unitId].map((rec, i) => (
                              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                                <div
                                  onClick={() => setFullscreenImage({ filePath: rec.filePath, fileName: rec.fileName })}
                                  style={{ width: 90, height: 90, borderRadius: 6, overflow: 'hidden', border: '1px solid #cbd5e1', cursor: 'pointer', background: '#f1f5f9', transition: 'opacity 0.2s' }}
                                  onMouseEnter={e => e.currentTarget.style.opacity = 0.8}
                                  onMouseLeave={e => e.currentTarget.style.opacity = 1}
                                >
                                  <img src={`/api/image?path=${encodeURIComponent(rec.filePath)}`} alt={rec.pointId} style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
                                </div>
                                <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600 }}>{rec.pointId}</div>
                                {rec.magnification && (
                                  <div style={{ fontSize: 9, color: '#94a3b8' }}>{rec.magnification}X · {rec.accelVolt}kV</div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {previewBond.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#898989', textTransform: 'uppercase', display: 'flex', justifyContent: 'space-between' }}>
                      <span>Bond Measurements ({previewBond.length})</span>
                    </div>
                    
                    {Object.entries(groupedBond).map(([testType, unitsObj]) => {
                       const units = Object.keys(unitsObj).sort((a,b) => parseInt(a) - parseInt(b));
                       const maxRows = Math.max(...units.map(u => unitsObj[u].length));
                       const rows = Array.from({ length: maxRows });

                       // Calculate stats
                       const stats = {};
                       units.forEach(u => {
                          const forces = unitsObj[u].map(x => parseFloat(x.force)).filter(x => !isNaN(x));
                          stats[u] = {
                             min: forces.length > 0 ? Math.min(...forces).toFixed(2) : '-',
                             max: forces.length > 0 ? Math.max(...forces).toFixed(2) : '-',
                             ave: forces.length > 0 ? (forces.reduce((a,b)=>a+b,0)/forces.length).toFixed(4) : '-'
                          };
                       });

                       return (
                         <div key={testType} style={{ overflowX: 'auto', border: '1px solid #d1d5db', background: '#fff' }}>
                           <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11, textAlign: 'center', fontFamily: 'sans-serif' }}>
                             <thead>
                               <tr style={{ background: '#e5e7eb' }}>
                                 <th style={{ border: '1px solid #d1d5db', padding: '4px' }}>No.</th>
                                 {units.map(u => (
                                   <React.Fragment key={u}>
                                     <th style={{ border: '1px solid #d1d5db', padding: '4px' }}>{testType} U-{u}</th>
                                     <th style={{ border: '1px solid #d1d5db', padding: '4px' }}>Mode</th>
                                   </React.Fragment>
                                 ))}
                               </tr>
                             </thead>
                             <tbody>
                               {rows.map((_, i) => (
                                 <tr key={i}>
                                   <td style={{ border: '1px solid #d1d5db', padding: '2px', background: '#f9fafb' }}>{i + 1}</td>
                                   {units.map(u => {
                                      const cell = unitsObj[u][i];
                                      return (
                                        <React.Fragment key={u}>
                                          <td style={{ border: '1px solid #d1d5db', padding: '2px' }}>{cell ? cell.force : ''}</td>
                                          <td style={{ border: '1px solid #d1d5db', padding: '2px' }}>{cell ? cell.grade : ''}</td>
                                        </React.Fragment>
                                      )
                                   })}
                                 </tr>
                               ))}
                               <tr style={{ background: '#f3f4f6', fontWeight: 'bold' }}>
                                 <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'left' }}>SPEC</td>
                                 {units.map(u => (
                                   <React.Fragment key={u}>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px', background: '#e0f2fe' }}></td>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px', background: '#fff' }}></td>
                                   </React.Fragment>
                                 ))}
                               </tr>
                               <tr style={{ background: '#f3f4f6', fontWeight: 'bold' }}>
                                 <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'left' }}>MIN</td>
                                 {units.map(u => (
                                   <React.Fragment key={u}>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'right' }}>{stats[u].min}</td>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px' }}></td>
                                   </React.Fragment>
                                 ))}
                               </tr>
                               <tr style={{ background: '#f3f4f6', fontWeight: 'bold' }}>
                                 <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'left' }}>MAX</td>
                                 {units.map(u => (
                                   <React.Fragment key={u}>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'right' }}>{stats[u].max}</td>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px' }}></td>
                                   </React.Fragment>
                                 ))}
                               </tr>
                               <tr style={{ background: '#f3f4f6', fontWeight: 'bold' }}>
                                 <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'left' }}>AVE</td>
                                 {units.map(u => (
                                   <React.Fragment key={u}>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'right' }}>{stats[u].ave}</td>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px' }}></td>
                                   </React.Fragment>
                                 ))}
                               </tr>
                               <tr style={{ background: '#e5e7eb', fontWeight: 'bold' }}>
                                 <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'left' }}>Result</td>
                                 {units.map(u => (
                                   <React.Fragment key={u}>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px', textAlign: 'center', background: '#dcfce3', color: '#059669' }}>-</td>
                                     <td style={{ border: '1px solid #d1d5db', padding: '4px', background: '#fff' }}></td>
                                   </React.Fragment>
                                 ))}
                               </tr>
                             </tbody>
                           </table>
                         </div>
                       )
                    })}
                  </div>
                )}

                {folder.name.includes('BS,WP,SP') && folder.hasBondAbility && previewBond.length === 0 && (
                   <div style={{ fontSize: 12, color: '#059669', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: 14 }}>📊</span> Bond Ability Excel Ready
                   </div>
                )}
             </div>
          )}
        </div>
      )}

      {fullscreenImage && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 2000,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40
        }} onClick={() => setFullscreenImage(null)}>
          <div style={{ position: 'relative', maxWidth: '100%', maxHeight: '100%' }} onClick={e => e.stopPropagation()}>
            <img 
              src={`/api/image?path=${encodeURIComponent(fullscreenImage.filePath)}`} 
              alt="fullscreen" 
              style={{ maxWidth: '100%', maxHeight: '80vh', objectFit: 'contain', borderRadius: 8, boxShadow: '0 10px 25px rgba(0,0,0,0.5)' }} 
            />
            <div style={{ color: '#fff', textAlign: 'center', marginTop: 12, fontSize: 14, fontFamily: 'monospace' }}>
              {fullscreenImage.fileName}
            </div>
            <button 
              onClick={() => setFullscreenImage(null)}
              style={{ position: 'absolute', top: -16, right: -16, background: '#ef4444', color: '#fff', border: 'none', borderRadius: '50%', width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: '0 4px 12px rgba(0,0,0,0.3)' }}
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Step2({ onBack, onNext, data }) {
  const [folders, setFolders] = React.useState([]);
  const [selected, setSelected] = React.useState({});
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    apiFetch(`/api/product-request/${data.pr}/${data.tp}/folders?lot=${encodeURIComponent(data.lot)}`)
      .then(r => r.json())
      .then(list => {
        setFolders(list);
        const initialSelected = {};
        list.forEach(f => {
          initialSelected[f.name] = true;
        });
        setSelected(initialSelected);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [data.pr, data.tp, data.lot]);

  const toggleFolder = (name) => {
    setSelected(prev => ({ ...prev, [name]: !prev[name] }));
  };

  return (
    <div>
      <div style={{ 
        display: 'flex', 
        gap: 24, 
        marginBottom: 12, 
        padding: '0 4px', 
        fontSize: 12, 
        color: '#898989',
        fontFamily: 'Inter, sans-serif'
      }}>
        <div>PR: <span style={{ color: '#4b5563', fontWeight: 500 }}>{data.pr}</span></div>
        <div>LOT: <span style={{ color: '#4b5563', fontWeight: 500 }}>{data.lot}</span></div>
        <div>DPA REPORT: <span style={{ color: '#4b5563', fontWeight: 500 }}>{data.tp}</span></div>
      </div>

      <Card style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <CalSans size={16}>Select Sections to Include</CalSans>
          <div style={{ fontSize: 12, color: '#898989' }}>
            {Object.values(selected).filter(v => v).length} / {folders.length} selected
          </div>
        </div>

        {loading ? (
          <div style={{ padding: '40px 0' }}><LoadingSpinner /></div>
        ) : folders.length > 0 ? (
          <div style={{ maxHeight: 500, overflowY: 'auto', paddingRight: 8 }}>
            {folders.map(f => (
              <SectionPreviewItem 
                key={f.name}
                folder={f}
                data={data}
                selected={!!selected[f.name]}
                onToggleSelect={toggleFolder}
              />
            ))}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#898989' }}>No images found for this lot.</div>
        )}
      </Card>


      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Btn variant="ghost" onClick={onBack}>← Back</Btn>
        <Btn variant="primary" onClick={() => onNext({ ...data, selectedSections: selected })} 
             disabled={loading || !Object.values(selected).some(v => v)}>Continue →</Btn>
      </div>
    </div>
  );
}

function Step3({ onBack, onRestart, data }) {
  const [phase, setPhase] = React.useState('idle');
  const [genStep, setGenStep] = React.useState(0);
  const [progress, setProgress] = React.useState(0);
  const [resultFile, setResultFile] = React.useState(null);
  const [bondExcelPath, setBondExcelPath] = React.useState(null);
  const [error, setError] = React.useState(null);

  const startGenerate = async () => {
    setPhase('generating'); setGenStep(0); setProgress(0); setError(null);
    
    // UI Progress Simulation while waiting for API
    const interval = setInterval(() => {
      setGenStep(prev => prev < GEN_STEPS.length - 2 ? prev + 1 : prev);
      setProgress(prev => prev < 80 ? prev + 10 : prev);
    }, 1500);

    try {
      const res = await apiFetch('/api/generate-report', {
        method: 'POST',
        body: JSON.stringify({
          prNumber: data.pr,
          timepoint: data.tp,
          lot: data.lot,
          selectedSections: data.selectedSections,
          userId: data.userId || 'System',
        }),
      });

      clearInterval(interval);

      if (res.ok) {
        const result = await res.json();
        setResultFile(result);
        setGenStep(GEN_STEPS.length - 1);
        setProgress(100);

        // Fetch Bond Ability Excel path
        apiFetch(`/api/bond-excel-path?pr_no=${data.pr}&timepoint=${data.tp}&lot=${data.lot}`)
          .then(r => r.json())
          .then(res => setBondExcelPath(res.path))
          .catch(() => {});

        setTimeout(() => setPhase('done'), 800);
      } else {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to generate report');
      }
    } catch (err) {
      clearInterval(interval);
      setError(err.message);
      setPhase('idle');
    }
  };

  const handleDownload = () => {
    if (!resultFile?.outputPath) return;
    const url = `/api/download-report?path=${encodeURIComponent(resultFile.outputPath)}`;
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', resultFile.filename || 'DPA_Report.pptx');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (phase === 'done') return (
    <Card>
      <div style={{ textAlign: 'center', padding: '16px 0' }}>
        <div style={{ width: 48, height: 48, borderRadius: '50%', background: '#242424', color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, margin: '0 auto 16px' }}>✓</div>
        <CalSans size={20} style={{ display: 'block', marginBottom: 8 }}>Report Generated Successfully</CalSans>
        <div style={{ fontSize: 14, color: '#898989', marginBottom: 24 }}>{resultFile?.filename}</div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginBottom: 24 }}>
          <Btn variant="primary" style={{ padding: '12px 24px' }} onClick={handleDownload}>
            📥 Download PPTX Report
          </Btn>
          {bondExcelPath && (
            <Btn variant="ghost" style={{ padding: '12px 24px', border: '1px solid #242424' }} 
                 onClick={() => window.open(`/api/download-report?path=${encodeURIComponent(bondExcelPath)}`, '_blank')}>
              📊 Download Bond Ability Excel
            </Btn>
          )}
        </div>
        <div>
          <Btn variant="ghost" onClick={onRestart}>Create Another</Btn>
        </div>
      </div>
    </Card>
  );

  return (
    <Card>
      {error && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 16, textAlign: 'center' }}>Error: {error}</div>}
      <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginBottom: phase === 'generating' ? 28 : 0 }}>
        <Btn variant="ghost" onClick={onBack} disabled={phase === 'generating'}>← Back</Btn>
        <Btn variant="primary" onClick={startGenerate} disabled={phase === 'generating'}>Create Report ▶</Btn>
      </div>
      {phase === 'generating' && (
        <div style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0, marginBottom: 16, flexWrap: 'wrap' }}>
            {GEN_STEPS.map((s, i) => (
              <React.Fragment key={s}>
                <span style={{ fontSize: 13, padding: '0 10px',
                  color: i < genStep ? '#898989' : i === genStep ? '#242424' : '#c0c0c0',
                  fontWeight: i === genStep ? 600 : 400,
                  textDecoration: i < genStep ? 'line-through' : 'none' }}>{s}</span>
                {i < GEN_STEPS.length - 1 && <span style={{ color: '#c0c0c0', fontSize: 12 }}>→</span>}
              </React.Fragment>
            ))}
          </div>
          <div style={{ height: 6, background: 'rgba(34,42,53,0.08)', borderRadius: 9999, overflow: 'hidden', maxWidth: 500, margin: '0 auto' }}>
            <div style={{ height: '100%', background: '#242424', borderRadius: 9999, width: `${progress}%`, transition: 'width 0.5s ease' }} />
          </div>
        </div>
      )}
    </Card>
  );
}

export function CreateReport({ user }) {
  const [step, setStep] = React.useState(1);
  const [stepData, setStepData] = React.useState({});
  const [prList, setPrList] = React.useState([]);
  const [prLoading, setPrLoading] = React.useState(true);

  React.useEffect(() => {
    apiFetch('/api/product-requests')
      .then(r => r.json())
      .then(data => {
        setPrList(data.map(p => ({ value: p.productRequestNo, label: p.productRequestNo })));
        setPrLoading(false);
      })
      .catch(() => setPrLoading(false));
  }, []);

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <CalSans size={32}>Create New Report</CalSans>
      </div>
      <div style={{ fontSize: 14, color: '#898989', marginBottom: 40 }}>
        Generate DPA report automatically.
      </div>
      <StepIndicator current={step} />
      {step === 1 && (
        <Step1
          onNext={(data) => { setStepData({ ...data, userId: user?.userId || 'System' }); setStep(2); }}
          prList={prList}
          prLoading={prLoading}
        />
      )}
      {step === 2 && (
        <Step2
          data={stepData}
          onBack={() => setStep(1)}
          onNext={(updatedData) => { setStepData(updatedData); setStep(3); }}
        />
      )}
      {step === 3 && (
        <Step3
          data={stepData}
          onBack={() => setStep(2)}
          onRestart={() => { setStep(1); setStepData({}); }}
        />
      )}
    </div>
  );
}
