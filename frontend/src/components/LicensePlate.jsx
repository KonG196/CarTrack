// A small Ukrainian-style licence plate: the blue UA strip on the left, black
// characters on white. Purely decorative — shows the car's own plate on the
// dashboard. Renders ONLY for the standard Ukrainian format ("AA 0000 AA");
// anything else (foreign/transit plates) or no plate → nothing at all, since the
// UA plate face would be wrong for them.
const UA_PLATE = /^([A-ZА-Я]{2})(\d{4})([A-ZА-Я]{2})$/;

function uaGroups(raw) {
  const m = raw.replace(/\s+/g, '').toUpperCase().match(UA_PLATE);
  return m ? `${m[1]} ${m[2]} ${m[3]}` : null;
}

export default function LicensePlate({ plate, className = '' }) {
  const grouped = plate ? uaGroups(plate) : null;
  if (!grouped) return null; // non-Ukrainian format or missing → don't show
  return (
    <span
      className={`inline-flex h-[22px] select-none items-stretch overflow-hidden rounded-[3px] bg-white text-black ring-1 ring-black/70 ${className}`}
      aria-label={plate}
    >

      <span className="flex w-[15px] flex-col items-center justify-center gap-0.5 bg-[#0057b7] leading-none">
        <span className="block h-[5px] w-[9px] overflow-hidden mr-[px] ">
          <span className="block h-[40%] w-full bg-[#4a90e2]" />
          <span className="block h-[40%] w-full bg-[#ffd500]" />
        </span>
        <span className="text-[7px] font-bold leading-none tracking-tight text-white"
        style={{ transform: 'scaleY(1.3)', transformOrigin: 'center' }}>
          UA
        </span>
      </span>
      
            <span className="flex flex-1 items-center justify-center px-1">
        <span
          className="font-sans text-[15px] font-bold leading-none tracking-[0.02em] text-black"
          style={{ transform: 'scaleY(1.2) translateY(-0.5px)', transformOrigin: 'center' }}
        >
          {grouped}
        </span>
      </span>
    </span>
  );
}
