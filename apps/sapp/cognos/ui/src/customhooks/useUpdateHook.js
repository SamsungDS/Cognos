const useUpdateHook = (setMemboxData, setShowFreeMemory, apiEndpoint) => {


  const handleUpdate = async (lmd, mem_mode) => {
    setShowFreeMemory(false);

    const updatePayload = { lmd: lmd, mem_mode: mem_mode };
    try {
      const response = await fetch(`${apiEndpoint}/update_lmd`, {
        mode: 'cors',
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify(updatePayload)
      });

      if (response.ok) {
        console.log("Successfully updated LMD: ", updatePayload);
        const data = await response.json();
        setMemboxData(data);
      }
    } catch (error) {
      console.error("Error updating LMD:", error);
    }
  };

  return { handleUpdate };
};

export default useUpdateHook;