"""Transistor SAR analog core generator; PDK cards supplied by caller.

All capacitors are ideal schematic capacitors in this initial implementation.
No foundry model coefficients are contained in this source.
"""

def generate_frontend(mos, prefix='sar', unit_cap=5e-15):
    lines = []
    inv, nand, and2, tg = [prefix+'_'+x for x in ('inv','nand2','and2','tg')]
    lines += ['subckt '+prefix+'_comparator vdd vss clk ip in q qb']
    devices = [('M1','p','ip','tail','vss',False,3e-6),
               ('M2','n','in','tail','vss',False,3e-6),
               ('M3','x','y','p','vss',False,1e-6),
               ('M4','y','x','n','vss',False,1e-6),
               ('M5','x','y','vdd','vdd',True,1e-6),
               ('M6','y','x','vdd','vdd',True,1e-6),
               ('M7','tail','clk','vss','vss',False,3e-6)]
    devices += [('MP'+node,node,'clk','vdd','vdd',True,1e-6) for node in ('p','n','x','y')]
    for name,d,g,s,b,p,w in devices:
        lines.append(mos(name,d,g,s,b,pmos=p,w=w,l=30e-9))
    # Isolate regeneration nodes from the state-dependent load of the SR latch.
    lines += ['XBX0 (vdd vss x xb) '+inv,
              'XBX1 (vdd vss xb xd) '+inv,
              'XBY0 (vdd vss y yb) '+inv,
              'XBY1 (vdd vss yb yd) '+inv,
              'XLQ (vdd vss xd qb q) '+nand,
              'XLQB (vdd vss yd q qb) '+nand,
              'ends '+prefix+'_comparator']
    lines += ['subckt '+prefix+'_cdac vdd vss refp refn vcm vip vin track '+
              ' '.join('b%d'%i for i in range(7,-1,-1))+' '+
              ' '.join('v%d'%i for i in range(7,-1,-1))+' vp vn',
              'XIT (vdd vss track trackb) '+inv]
    # Six micrometres per polarity, using two independently netlisted 3um cards.
    for side,source in (('p','vip'),('n','vin')):
        for j in range(2):
            lines.append(mos('MSN%s%d'%(side,j),'v'+side,'track',source,'vss',False,3e-6,30e-9))
            lines.append(mos('MSP%s%d'%(side,j),'v'+side,'trackb',source,'vdd',True,3e-6,30e-9))
        lines.append('CDUMMY%s (v%s vcm) capacitor c=%.16g'%(side,side,unit_cap))
    for bit in range(7,-1,-1):
        k=str(bit)
        lines += ['XVALID'+k+' (vdd vss v'+k+' trackb e'+k+') '+and2,
                  'XEI'+k+' (vdd vss e'+k+' eb'+k+') '+inv,
                  'XBI'+k+' (vdd vss b'+k+' bb'+k+') '+inv,
                  'XHI'+k+' (vdd vss e'+k+' b'+k+' hi'+k+') '+and2,
                  'XLO'+k+' (vdd vss e'+k+' bb'+k+' lo'+k+') '+and2,
                  'XHIB'+k+' (vdd vss hi'+k+' hib'+k+') '+inv,
                  'XLOB'+k+' (vdd vss lo'+k+' lob'+k+') '+inv]
        for side in ('p','n'):
            bottom='bot'+side+k
            lines.append('C'+side+k+' (v'+side+' '+bottom+') capacitor c=%.16g'%(unit_cap*2**bit))
            # Unresolved=VCM; b=1 subtracts a positive differential DAC step.
            refs=('refn','refp') if side=='p' else ('refp','refn')
            for tag,ref,gate,gateb in [('H',refs[0],'hi'+k,'hib'+k),
                                      ('L',refs[1],'lo'+k,'lob'+k),
                                      ('M','vcm','eb'+k,'e'+k)]:
                lines.append(mos('MN'+tag+side+k,bottom,gate,ref,'vss',False,3e-6,30e-9))
                lines.append(mos('MP'+tag+side+k,bottom,gateb,ref,'vdd',True,3e-6,30e-9))
    lines += ['ends '+prefix+'_cdac']
    return '\n'.join(lines)+'\n'
