import re
import os
import argparse
from matplotlib.pyplot import figure, show
import matplotlib.pyplot as plt
import matplotlib as mp
import numpy as np
import fileinput
from matplotlib.ticker import MaxNLocator

def remove_creation_date(file_name):
    for line in fileinput.input(file_name, inplace=True):
        if not 'CreationDate' in line:
            print line,


# define command line arguments
parser = argparse.ArgumentParser(
    description='Post-Process timing/memory info and plot figures.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--prefix', metavar='prefix', default='LIKWID_Emmy_RRZE',
                    help='A folder to look for benchmark results')
parser.add_argument('--dim', metavar='dim', default=2, type=int,
                    help='Dimension (2 or 3)')
parser.add_argument('--breakdown', help='Post process breakdown results of vmult', action="store_true")

args = parser.parse_args()

prefix = args.prefix if args.prefix.startswith('/') else os.path.join(os.getcwd(), args.prefix)
if args.breakdown:
    prefix = prefix + '_breakdown'

files = []
for root, dirs, files_ in os.walk(prefix):
    for f in files_:
        if f.endswith(".toutput"):
            files.append(os.path.join(root, f))

print 'Gather data from {0}'.format(prefix)
print 'found {0} files'.format(len(files))

pattern = r'[+\-]?(?:[0-9]\d*)(?:\.\d*)?(?:[eE][+\-]?\d+)?'

# Sections to pick up from
#|                 Metric                 |     Sum    |    Min    |     Max    |    Avg    |  %ile 25  |  %ile 50  |  %ile 75  |
# table:
sections = [
    'MFLOP/s STAT',
    'Memory bandwidth [MBytes/s] STAT',
    'Operational intensity STAT',
    'Runtime (RDTSC) [s] STAT'
]

# NODE data:
clock_speed = 2.2  # GHz
# memory bandwidth
# likwid-bench -t load_avx -w S0:1GB:10:1:2
B=47.16855 # 50 GB/s single socket

print 'Peak performance calculations:'
P = clock_speed
print '  Clock speed:  {0}'.format(clock_speed)
P = P * 2                             # add+mult per cycle
print '  w FMA:        {0}'.format(P)
P = P * 4                             # vectorization over 4 doubles = 256 bits (AVX), VECTORIZATION_LEVEL=2
print '  w FMA w SIMD: {0}'.format(P)
P = P * 10                            # 10 cores
print '  peak:         {0}'.format(P)

table_names = [
    'Event',
    'Metric'
]

likwid_data = []

regions = []
if args.breakdown:
    regions = [
        'vmult_sum_factorization',
        'vmult_reinit_read_write',
        'vmult_quadrature_loop'
    ]

# labels/colors to be used for regions in breakdown run:
region_labels = [
    'sum factorization',
    'read / write',
    'quadrature loop'
]
region_colors = [
    'b',
    'g',
    'c'
]

for f in files:
    # guess parameters from the file name:
    fname = os.path.basename(f)
    strings = fname.split('_')
    dim = int(re.findall(pattern,strings[2])[0])
    p   = int(re.findall(pattern,strings[3])[0])
    q   = int(re.findall(pattern,strings[3])[1])
    if not args.breakdown:
        regions = [
            'vmult_MF' if 'MF_CG' in f else 'vmult_Trilinos'
        ]
    label = ''
    color = ''  # use colors consistent with post_process.py
    if 'MF_CG' in fname:
        if '_scalar' in fname:
            label = 'MF scalar'
            color = 'b'
        elif '_tensor2' in fname:
            label = 'MF tensor2'
            color = 'g'
        elif '_tensor4' in fname:
            label = 'MF tensor4'
            color = 'c'
    else:
        label = 'Trilinos'
        color = 'r'

    print 'dim={0} p={1} q={2} region={3} label={4} color={5} file={6}'.format(dim,p,q,regions[0],label,color,fname)

    fin = open(f, 'r')

    # store data for each requested section and region here:
    timing = [ [ np.nan for i in range(len(sections))] for i in range(len(regions))]

    found_region = False
    found_table = False
    r_idx = np.nan
    for line in fin:
        # Check if we found one of the regions:
        if 'Region:' in line:
            found_region = False
            for idx, s in enumerate(regions):
                if s in line:
                    found_region = True
                    r_idx = idx

        # Reset the table if found any table:
        for t in table_names:
            if t in line:
                found_table = False

        # Now check if the table is actually what we need
        if found_region and ('Metric' in line) and ('Sum' in line):
            found_table = True
            print '-- Region {0} {1}'.format(regions[r_idx], r_idx)

        # Only if we are inside the table of interest and region of interest, try to match the line:
        if found_table and found_region:
            columns = [s.strip() for s in line.split('|')]
            if len(columns) > 1:
                for idx, s in enumerate(sections):
                    if s == columns[1]:
                        val = float(columns[2])
                        print '   {0} {1}'.format(s,val)
                        # we should get here only once for each region:
                        assert np.isnan(timing[r_idx][idx])
                        timing[r_idx][idx] = val

    # finish processing the file, put the data
    for r_idx in range(len(regions)):
        t = timing[r_idx]
        # overwrite label/color if we do breakdown:
        if args.breakdown:
            label = region_labels[r_idx]
            color = region_colors[r_idx]
        tp = tuple((dim,p,q,label,color,t))
        likwid_data.append(tp)

# now we have lists of tuples ready
# first, sort by label:
likwid_data.sort(key=lambda tup: (tup[3], tup[1]))

#####################
#       PLOT        #
#####################

params = {'legend.fontsize': 14,
          'font.size': 20}
plt.rcParams.update(params)

# Roofline model
# p = min (P, b I)
# where I is measured intensity (Flops/byte)
def Roofline(I,P,B):
    return np.array([min(P,B*i) for i in I])

x = np.linspace(1./B, 10. if not args.breakdown else 100., num=500 if not args.breakdown else 5000)
base = np.array([1./B for i in x])
roofline_style = 'b-'
peak = Roofline(x,P,B)
# see https://github.com/matplotlib/matplotlib/issues/8623#issuecomment-304892552
plt.loglog(x,peak, roofline_style, label=None, nonposx='clip', nonposy='clip')

# various ceilings (w/o FMA, w/o FMA and vectorization):
for p_ in [P/2, P/2/4]:
    plt.plot(x,Roofline(x,p_,B), roofline_style, label=None)

plt.fill_between(x, base, peak, where=peak>base, interpolate=True, zorder=1, color='aqua', alpha=0.1)

plt.grid(True, which="both",color='grey', linestyle=':', zorder=5)


# map degrees to point labels:
degree_to_points = {
    2:'s',
    4:'o',
    6:'^',
    8:'v'
}

mf_perf = []
tr_perf = []

# Now plot each measured point:
for d in likwid_data:
  if d[0] == args.dim:
    f = d[5][0]
    b = d[5][1]
    x = [f/b]
    y = [f/1000]  # MFLOP->GFLOP
    style = d[4] + degree_to_points[d[1]]
    label = '{0} (p={1})'.format(d[3],d[1])
    plt.loglog(x,y, style, label=label)
    if 'MF' in label:
      mf_perf.append(y[0])
    else:
      tr_perf.append(y[0])

plt.xlabel('intensity (Flop/byte)')
plt.ylabel('performance (GFlop/s)')
plt.ylim(top=300,bottom=1)

ang = 42 if not args.breakdown else 50
y_pos = 5 if not args.breakdown else 7
plt.text(0.02, y_pos, 'B={:.1f} GB/s'.format(B), rotation=ang)

x_pos = 3.7 if not args.breakdown else 25
plt.text(x_pos,200,'Peak DP', fontsize=14)
plt.text(x_pos,100,'w/o FMA', fontsize=14)
plt.text(x_pos,25, 'w/o SIMD', fontsize=14)

leg = plt.legend(loc='upper left', ncol=1, labelspacing=0.1)


# file location
fig_prefix = os.path.join(os.getcwd(), '../doc/' + os.path.basename(os.path.normpath(prefix)) + '_')

name = 'roofline_breakdown_{0}d.pdf' if args.breakdown else 'roofline_{0}d.pdf'

fig_file = fig_prefix + name.format(args.dim)

print 'Saving figure in: {0}'.format(fig_file)

plt.tight_layout()
plt.savefig(fig_file, format='pdf')  # pdf has better colors
# remove_creation_date(fig_file)

# Finally report average performance for all MF and Trilinos runs:
print 'Average performance:'
print '  MF:       {0}'.format(np.mean(mf_perf))
print '  Trilinos: {0}'.format(np.mean(tr_perf))
