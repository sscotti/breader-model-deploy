window.config = {
    // Measurement tracking workflow: 'standard' | 'simplified' | 'none' (OHIF 3.9+)
    // 'none' = no tracking; annotations stay untracked (no SR export workflow from tracking).
    measurementTrackingMode: 'simplified',
    // Keys must exist (arrays). Omitting them leaves appConfig.extensions undefined → Symbol.iterator error.
    // Empty [] is valid here: Orthanc OHIF merges user config with built-in defaults; CXAS Basic Text SR
    // still renders (Plan of care note, CTR, SCD, etc.). Only add explicit extension ids if you need
    // to override the bundled list.
    extensions: [],
    modes: [],
    customizationService: [
        {
            measurementLabels: {
                $set: {
                    labelOnMeasure: false,
                    exclusive: false,
                    items: [
                        { value: 'Pleural effusion', label: 'Pleural effusion' },
                        { value: 'Pneumothorax', label: 'Pneumothorax' },
                        { value: 'Mass', label: 'Mass' },
                        { value: 'Nodule', label: 'Nodule' }
                    ]
                }
            }
        }
    ]
};