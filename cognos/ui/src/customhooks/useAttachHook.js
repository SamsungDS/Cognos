const useAttachHook = (setMemboxData, setLmdData, handleAttachMemoryToggle, selectedValue, apiEndpoint, logicalMemoryDevice) => {
  const handleAttach = async (formData) => {
    handleAttachMemoryToggle();
    const { label } = selectedValue;
    const obj = { host_name: label, dev_name: logicalMemoryDevice };
    const attachMem = { ...formData, ...obj };


    try {
      const response = await fetch(`${apiEndpoint}/attach_device`, {
        mode: 'cors',
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'accept': 'application/json',
          'Access-Control-Allow-Origin':'*'
        },
        body: JSON.stringify(attachMem)
      });

      if (response.ok) {
        const data = await response.json();
        setLmdData(data);
      }
    } catch (error) {
      console.error("Operation failed", error);
   }

    try {
      const response = await fetch(`${apiEndpoint}/devices`, {
        mode: 'cors',
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'accept': 'application/json',
          'Access-Control-Allow-Origin':'*'
        },
        body: JSON.stringify({
          "input": "cluster_id=CLUST1;command=ListDevices;FM_id=203;FM_endpoint=samsung.com"
        })
      });

      if (response.ok) {
        const boxdata = await response.json();
        setMemboxData(boxdata);
      }
    } catch (error) {
      
    }
  };

  return { handleAttach };
};

export default useAttachHook;