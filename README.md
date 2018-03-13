# TreeSAPP: Tree-based Sensitive and Accurate Phylogenetic Profiling

Connor Morgan-Lang, Kishori M. Konwar, Young C. Song, and Steven J. Hallam

## Overview:

A python pipeline for identifying marker genes in a metagenome and grafting sequences onto reference phylogenetic trees.

## Download and installation:

For an easy introduction to TreeSAPP, please refer to the [GCP tutorial]().

```
git clone git@github.com:hallamlab/TreeSAPP.git
```
The exectutables for the required softwares are included either in the TreeSAPP/sub_binaries/mac
 directory or TreeSAPP/sub_binaries/ubuntu, depending on your OS.
If these do not work out-of-the-box, instructions on installing the dependencies specific to your
 machine are included below. We currently support Red Hat Enterprise Linux, Ubuntu (14.04), and Mac OS (10.6-10.8).

To finish installing in a local directory, use:
```
make
make install
```

### Downloading dependencies for Linux:

#### RAxML:
A simple `git clone` of their [github page](https://github.com/stamatak/standard-RAxML) should work 
for Linux and Mac operating systems. From here, consult the README file in the standard-RAxML directory for
installation instructions using make.
We have tested several versions and found no problems from V.7.1 to the most recent release as of 
December 1st, 2015. However, the executable MUST be named `raxmlHPC` or it will not be found by TreeSAPP!
If you find an incompatibility please notify us through the Issues feed!

#### Gblocks:
For Linux/x86:
```
cd path/to/TreeSAPP/sub_binaries/
tar xzf Gblocks_Linux_0.91b.tar.Z
rm Gblocks
ln -s Gblocks_0.91b/Gblocks ./
```

If you get a segmentation fault, try the executable in Gblocks_Linux64_0.91b.tar.Z.

#### Genewise:
On Ubuntu you can install the wise package with apt-get:
```
sudo apt-get install wise
```
Or try to install wise from source
```
wget http://www.ebi.ac.uk/~birney/wise2/wise2.4.1.tar.gz
tar xzf wise2.4.1.tar.gz
rm wise2.4.1.tar.gz
cd wise2.4.1/src/
make all
```
If you have problems involving `getline` being previously declared in sqio.c,
use your text editor of choice to replace all instances of `getline` with a new function name such as `getline_new`.
Other installation issues may be taken care of elsewhere. We also suggest changing line 25 in wise2.4.1/src/makefile
and line 84 in wise2.4.1/src/dynlibsrc/makefile from `CC = cc` to `CC = gcc` to make compilation more smooth on modern
systems.

For RHEL 7, we have included the source rpm file in ~/TreeSAPP/sub_binaries/wise2-2.2.0-14.el7.src.rpm. You can install this file as root with:
```
sudo rpmbuild --rebuild wise2-2.2.0-14.el7.src.rpm
rpm -ivv /root/rpmbuild/RPMS/x86_64/wise2-2.2.0-14.el7.x86_64.rpm
rpm -ql wise2
```
NOTE: the paths may not be identical here, but the commands to build the source rpm, install it, and locate the genewise binary are standard. 

#### HMMER
hmmalign is the only HMMER module required by TreeSAPP, but HMMER3 is incompatible with this
version of TreeSAPP. HMMER 2.4 works and can be downloaded from
http://hmmer.janelia.org/download.html.

### Running TreeSAPP

To list all the options with brief help statements `./mltreemap.py -h`.

To perform a basic run with only the required arguments:
```
./treesapp.py -i input.fasta -o ~/path/to/output/directory/
```
Executables are automatically detected in both the $PATH and in the
sub_binaries/mac or sub_binaries/ubuntu, depending on your OS. However, if your executables
are together elsewhere, TreeSAPP can be directed to them with `--executables`.
If WISECONFIGDIR is not already set, treesapp.py will exit and provide you with the correct command to
add this to you environment.

### Using imagemaker_2_061/mltreemap_imagemaker.pl

We packaged the original MLTreeMap perl code with TreeSAPP for continuity's sake

To use it, some perl dependencies may need to be installed. For instance, the commands
```
cpan
install "SVG"
install "Math::Trig"
```
may be necessary. Two perl module files (\*.pm) are included in imagemaker_2_061/lib: NEWICK_tree.pm and MLTreeMap_ml_svg_visualizer.pm.
These will need to be copied to somewhere in your perl path (such as /usr/lib/perl5/) to allow mltreemap_imagemaker.pl to work anywhere
on your machine.  

