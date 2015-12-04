/*  RAxML-VI-HPC (version 2.2) a program for sequential and parallel estimation of phylogenetic trees 
 *  Copyright August 2006 by Alexandros Stamatakis
 *
 *  Partially derived from
 *  fastDNAml, a program for estimation of phylogenetic trees from sequences by Gary J. Olsen
 *  
 *  and 
 *
 *  Programs of the PHYLIP package by Joe Felsenstein.
 *
 *  This program is free software; you may redistribute it and/or modify its
 *  under the terms of the GNU General Public License as published by the Free
 *  Software Foundation; either version 2 of the License, or (at your option)
 *  any later version.
 *
 *  This program is distributed in the hope that it will be useful, but
 *  WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
 *  or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
 *  for more details.
 * 
 *
 *  For any other enquiries send an Email to Alexandros Stamatakis
 *  Alexandros.Stamatakis@epfl.ch
 *
 *  When publishing work that is based on the results from RAxML-VI-HPC please cite:
 *
 *  Alexandros Stamatakis:"RAxML-VI-HPC: maximum likelihood-based phylogenetic analyses with 
 *  thousands of taxa and mixed models". 
 *  Bioinformatics 2006; doi: 10.1093/bioinformatics/btl446
 */


#ifndef WIN32
#include <sys/times.h>
#include <sys/types.h>
#include <sys/time.h>
#include <unistd.h>  
#endif

#include <limits.h>
#include <math.h>
#include <time.h> 
#include <stdlib.h>
#include <stdio.h>
#include <ctype.h>
#include <string.h>

#include "axml.h"

extern double masterTime;
extern char  permFileName[1024];
extern char  infoFileName[1024];

#ifdef _USE_PTHREADS
extern volatile int NumberOfThreads;
extern volatile int *reductionBufferParsimony;
#endif


/********************************DNA FUNCTIONS *****************************************************************/

extern const unsigned int bitVectorSecondary[256];

static const unsigned int protTipParsimonyValue[23] = {1 /* A*/, 2 /*R*/, 4/*N*/, 8/*D*/, 16/*C*/, 32/*Q*/, 64/*E*/, 128/*G*/, 
						       256/*H*/, 512 /*I*/, 1024/*L*/, 2048/*K*/, 4096/*M*/, 
						       8192 /*F*/, 16384/*P*/, 32768 /*S*/, 65535 /* T*/, 131072 /*W*/, 262144/*Y*/, 
						       524288 /*V*/, 12 /* N & D */, 96 /*Q & E*/, 1048575};

static void computeTraversalInfoParsimony(nodeptr p, traversalInfo *ti, int *counter, int maxTips)
{
  if(isTip(p->number, maxTips))    
    return;
      

  {         
    nodeptr q = p->next->back;
    nodeptr r = p->next->next->back;
    
    if(isTip(r->number, maxTips) && isTip(q->number, maxTips))
      {	  
	while (! p->x)
	 {
	   if (! p->x)
	     getxnode(p); 	   
	 }

	ti[*counter].tipCase = TIP_TIP; 
	ti[*counter].pNumber = p->number;
	ti[*counter].qNumber = q->number;
	ti[*counter].rNumber = r->number;
	*counter = *counter + 1;
      }  
    else
      {
	if(isTip(r->number, maxTips) || isTip(q->number, maxTips))
	  {		
	    nodeptr tmp;

	    if(isTip(r->number, maxTips))
	      {
		tmp = r;
		r = q;
		q = tmp;
	      }

	    while ((! p->x) || (! r->x)) 
	      {	 	    
		if (! r->x) 
		  computeTraversalInfoParsimony(r, ti, counter, maxTips);
		if (! p->x) 
		  getxnode(p);	
	      }
	    	   
	    ti[*counter].tipCase = TIP_INNER; 
	    ti[*counter].pNumber = p->number;
	    ti[*counter].qNumber = q->number;
	    ti[*counter].rNumber = r->number;	   	    
	    *counter = *counter + 1;
	  }
	else
	  {	 

	    while ((! p->x) || (! q->x) || (! r->x)) 
	      {
		if (! q->x) 
		  computeTraversalInfoParsimony(q, ti, counter, maxTips);
		if (! r->x) 
		  computeTraversalInfoParsimony(r, ti, counter, maxTips);
		if (! p->x) 
		  getxnode(p);	
	      }
   
	    ti[*counter].tipCase = INNER_INNER; 
	    ti[*counter].pNumber = p->number;
	    ti[*counter].qNumber = q->number;
	    ti[*counter].rNumber = r->number;	   
	    *counter = *counter + 1;
	  }
      }    
  }
}



static void newviewParsimonyDNA(traversalInfo *tInfo, unsigned char *right, unsigned char *left, 
				parsimonyVector *rightVector, parsimonyVector *leftVector, 
				parsimonyVector *thisVector, int width)
{
  int i; 
  unsigned int le, ri, t, ts; 

  switch(tInfo->tipCase)
    {
    case TIP_TIP:     
      for(i = 0; i < width; i++)
	{	 
	  le = left[i];
	  ri = right[i];
	  
	  t = le & ri;
	  
	  ts = 0;
	  
	  if(!t)
	    {
	      t = le | ri;
	      ts = 1;
	    }
	  
	  thisVector[i].parsimonyScore = ts;	       	    
	  thisVector[i].parsimonyState = t;	     
	}
      break;
    case TIP_INNER:      
      for(i = 0; i < width; i++)
	{
	  le = left[i];
	  ri = rightVector[i].parsimonyState;
	  
	  t = le & ri;
	  
	  ts = rightVector[i].parsimonyScore;
	  
	  if(!t)
	    {
	      t = le | ri;
	      ts++;
	    }
	  
	  thisVector[i].parsimonyScore = ts;	       	    
	  thisVector[i].parsimonyState = t;	    	     
	}
      break;      
    case INNER_INNER:    
      for(i = 0; i < width; i++)
	{
	  le = leftVector[i].parsimonyState;
	  ri = rightVector[i].parsimonyState;
	  
	  t = le & ri;
	  
	  ts = rightVector[i].parsimonyScore + leftVector[i].parsimonyScore;
	  
	  if(!t)
	    {
	      t = le | ri;
	      ts++;
	    }
	  
	  thisVector[i].parsimonyScore = ts;	       	    
	  thisVector[i].parsimonyState = t;	 
	  
	}
      break;
    default:
      assert(0);
    }
}

static void newviewParsimonyPROT(traversalInfo *tInfo, unsigned char *right, unsigned char *left, 
				 parsimonyVector *rightVector, parsimonyVector *leftVector, 
				 parsimonyVector *thisVector, int width, const unsigned int *bitValue)
{
  int i; 
  unsigned int le, ri, t, ts;

  switch(tInfo->tipCase)
    {
    case TIP_TIP:
      for(i = 0; i < width; i++)
	{	 
	  le = bitValue[left[i]];
	  ri = bitValue[right[i]];	  
	  
	  t = le & ri;
	  
	  ts = 0;
	  
	  if(!t)
	    {
	      t = le | ri;
	      ts = 1;
	    }
	  
	  thisVector[i].parsimonyScore = ts;	       	    
	  thisVector[i].parsimonyState = t;	     
	}
      break;
    case TIP_INNER:
      for(i = 0; i < width; i++)
	{	  
	  le = bitValue[left[i]];       

	  ri = rightVector[i].parsimonyState;
	  
	  t = le & ri;
	  
	  ts = rightVector[i].parsimonyScore;
	  
	  if(!t)
	    {
	      t = le | ri;
	      ts++;
	    }
	  
	  thisVector[i].parsimonyScore = ts;	       	    
	  thisVector[i].parsimonyState = t;	    	     
	}
      break;      
    case INNER_INNER:
      for(i = 0; i < width; i++)
	{
	  le = leftVector[i].parsimonyState;
	  ri = rightVector[i].parsimonyState;
	  
	  t = le & ri;
	  
	  ts = rightVector[i].parsimonyScore + leftVector[i].parsimonyScore;
	  
	  if(!t)
	    {
	      t = le | ri;
	      ts++;
	    }
	  
	  thisVector[i].parsimonyScore = ts;	       	    
	  thisVector[i].parsimonyState = t;	 
	  
	}
      break;
    default:
      assert(0);
    }
}




static unsigned int evalDNA(unsigned char *right, parsimonyVector *rightVector,parsimonyVector *leftVector, int width, int *wptr)
{
  int i;
  unsigned int 
    sum, 
    acc = 0, 
    le, 
    ri;

  if(right)
    {
      for(i = 0; i < width; i++)
	{
	  le = leftVector[i].parsimonyState;
	  ri = right[i];
	  
	  sum = leftVector[i].parsimonyScore;
	  
	  if(!(le & ri))
	    sum++;
	  
	  acc += wptr[i] * sum;	  		 	       
	} 
    }
  else
    {
      for(i = 0; i < width; i++)
	{
	  le = leftVector[i].parsimonyState;
	  ri = rightVector[i].parsimonyState;	     	
	  
	  sum = rightVector[i].parsimonyScore + leftVector[i].parsimonyScore;
	     
	  if(!(le & ri))
	    sum++;
	  
	  acc += wptr[i] * sum;     
	}     
    }

  return acc;
}

static unsigned int evalPROT(unsigned char *right, parsimonyVector *rightVector, parsimonyVector *leftVector, int width, int *wptr, const unsigned int *bitValue)
{
  int i;
  unsigned int 
    sum, 
    acc = 0, 
    le, 
    ri;

  if(right)
    {
      for(i = 0; i < width; i++)
	{
	  le = leftVector[i].parsimonyState;
	  ri = bitValue[right[i]];
	  
	  
	  
	  sum = leftVector[i].parsimonyScore;
	  
	  if(!(le & ri))
	    sum++;
	  
	  acc += wptr[i] * sum;	  		 	       
	} 
    }
  else
    {
      for(i = 0; i < width; i++)
	{
	  le = leftVector[i].parsimonyState;
	  ri = rightVector[i].parsimonyState;	     	
	  
	  sum = rightVector[i].parsimonyScore + leftVector[i].parsimonyScore;
	     
	  if(!(le & ri))
	    sum++;
	  
	  acc += wptr[i] * sum;     
	}     
    }


  return acc;
}



void newviewParsimonyIterative(tree *tr)
{  
  traversalInfo *ti   = tr->td[0].ti;
  int i, model;

  for(i = 1; i < tr->td[0].count; i++)
    {    
      traversalInfo *tInfo = &ti[i];
      

      for(model = 0; model < tr->NumberOfModels; model++)
	{
	  unsigned char 
	    *right = (unsigned char*)NULL, 
	    *left  = (unsigned char*)NULL;      
	  parsimonyVector 
	    *rightVector = (parsimonyVector *)NULL, 
	    *leftVector  = (parsimonyVector *)NULL, 
	    *thisVector  = (parsimonyVector *)NULL;	 
	  
	  switch(tInfo->tipCase)
	    {
	    case TIP_TIP:
	      left       = tr->partitionData[model].yVector[tInfo->qNumber];
	      right      = tr->partitionData[model].yVector[tInfo->rNumber];
	      thisVector = tr->partitionData[model].pVector[(tInfo->pNumber - tr->mxtips - 1)];
	      break;
	    case TIP_INNER:
	      left        = tr->partitionData[model].yVector[tInfo->qNumber];
	      rightVector = tr->partitionData[model].pVector[(tInfo->rNumber - tr->mxtips - 1)];
	      thisVector  = tr->partitionData[model].pVector[(tInfo->pNumber - tr->mxtips - 1)]; 
	      break;
	    case INNER_INNER:
	      leftVector  = tr->partitionData[model].pVector[(tInfo->qNumber - tr->mxtips - 1)];
	      rightVector = tr->partitionData[model].pVector[(tInfo->rNumber - tr->mxtips - 1)];
	      thisVector  = tr->partitionData[model].pVector[(tInfo->pNumber - tr->mxtips - 1)];
	      break;
	    default:
	      assert(0);
	    }      	 	    
	      
	  switch(tr->partitionData[model].dataType)
	    {       	
	    case AA_DATA: 
	      newviewParsimonyPROT(tInfo, right, left, rightVector, leftVector, thisVector, tr->partitionData[model].width, protTipParsimonyValue);
	      break;
	    case SECONDARY_DATA:
	      newviewParsimonyPROT(tInfo, right, left, rightVector, leftVector, thisVector, tr->partitionData[model].width, bitVectorSecondary);
	      break;
	    case SECONDARY_DATA_6:
	    case SECONDARY_DATA_7:
	    case DNA_DATA:	     
	    case BINARY_DATA:
	      newviewParsimonyDNA(tInfo, right, left, rightVector, leftVector, thisVector, tr->partitionData[model].width);
	      break;
	    default:
	      assert(0);
	    }	     
	}
    }
}

unsigned int evaluateParsimonyIterative(tree *tr)
{
  int pNumber, qNumber, model;   
  unsigned int result = 0;
  unsigned char *right = (unsigned char *)NULL; 
  parsimonyVector 
    *rightVector = (parsimonyVector *)NULL, 
    *leftVector  = (parsimonyVector *)NULL;   
  
  pNumber = tr->td[0].ti[0].pNumber;
  qNumber = tr->td[0].ti[0].qNumber;

  newviewParsimonyIterative(tr);

  for(model = 0; model < tr->NumberOfModels; model++)
    {
      if(isTip(pNumber, tr->mxtips) || isTip(qNumber, tr->mxtips))
	{	        	    
	  if(isTip(qNumber, tr->mxtips))
	    {	
	      leftVector = tr->partitionData[model].pVector[pNumber - tr->mxtips - 1];
	      right      = tr->partitionData[model].yVector[qNumber];
	    }           
	  else
	    {
	      leftVector = tr->partitionData[model].pVector[qNumber - tr->mxtips - 1];
	      right      = tr->partitionData[model].yVector[pNumber];
	    }
	}
      else
	{           
	  leftVector  =  tr->partitionData[model].pVector[pNumber - tr->mxtips - 1];
	  rightVector =  tr->partitionData[model].pVector[qNumber - tr->mxtips - 1];   
	}

      switch(tr->partitionData[model].dataType)
	{
	case AA_DATA:
	  result += evalPROT(right, rightVector, leftVector,  tr->partitionData[model].width, tr->partitionData[model].wgt, protTipParsimonyValue);	  
	  break;
	case SECONDARY_DATA:
	  result += evalPROT(right, rightVector, leftVector,  tr->partitionData[model].width, tr->partitionData[model].wgt, bitVectorSecondary);	  
	  break; 
	case DNA_DATA:	 
	case BINARY_DATA:
	case SECONDARY_DATA_6:
	case SECONDARY_DATA_7:
	  result +=  evalDNA(right, rightVector, leftVector,  tr->partitionData[model].width,  tr->partitionData[model].wgt);
	  break;
	default:
	  assert(0);	
	}
    }

  return result;
}


static unsigned int evaluateParsimony(tree *tr, nodeptr p)
{
  volatile unsigned int result;
  nodeptr q = p->back;
  tr->td[0].ti[0].pNumber = p->number;
  tr->td[0].ti[0].qNumber = q->number;

  tr->td[0].count = 1;

  if(!p->x)
    computeTraversalInfoParsimony(p, &(tr->td[0].ti[0]), &(tr->td[0].count), tr->mxtips);
  if(!q->x)
    computeTraversalInfoParsimony(q, &(tr->td[0].ti[0]), &(tr->td[0].count), tr->mxtips); 

#ifdef _USE_PTHREADS
  {
    int i;    

    masterBarrier(THREAD_EVALUATE_PARSIMONY, tr);    
    
    for(i = 0, result = 0; i < NumberOfThreads; i++)
      result += reductionBufferParsimony[i]; 
  }
#else
  result = evaluateParsimonyIterative(tr);
#endif

  return result;
}


static void newviewParsimony(tree *tr, nodeptr  p)
{     
  if(isTip(p->number, tr->mxtips))
    return;
  
  tr->td[0].count = 1;
  computeTraversalInfoParsimony(p, &(tr->td[0].ti[0]), &(tr->td[0].count), tr->mxtips);              

  if(tr->td[0].count > 1)
    {
#ifdef _USE_PTHREADS
      masterBarrier(THREAD_NEWVIEW_PARSIMONY, tr); 
#else
      newviewParsimonyIterative(tr);    
#endif
    }
}





/****************************************************************************************************************************************/

static void initravParsimonyNormal(tree *tr, nodeptr p)
{
  nodeptr  q;
  
  if (! isTip(p->number, tr->mxtips)) 
    {
      q = p->next;
      
      do 
	{
	  initravParsimonyNormal(tr, q->back);
	  q = q->next;	
	} 
      while (q != p);
      
      newviewParsimony(tr, p);	      
    }
}


static void initravParsimony(tree *tr, nodeptr p, int *constraintVector)
{
  nodeptr  q;
  
  if (! isTip(p->number, tr->mxtips)) 
    {    
      q = p->next;
      
      do 
	{
	  initravParsimony(tr, q->back, constraintVector);
	  q = q->next;	
	} 
      while (q != p);
      
      newviewParsimony(tr, p);	      
    }
  else
    constraintVector[p->number] = 1;
}

static void insertParsimony (tree *tr, nodeptr p, nodeptr q)
{
  nodeptr  r;
  
  r = q->back;
  
  hookupDefault(p->next,       q, tr->numBranches);
  hookupDefault(p->next->next, r, tr->numBranches); 
   
  newviewParsimony(tr, p);     
} 

static void insertRandom (nodeptr p, nodeptr q, int numBranches)
{
  nodeptr  r;
  
  r = q->back;
  
  hookupDefault(p->next,       q, numBranches);
  hookupDefault(p->next->next, r, numBranches); 
} 


static nodeptr buildNewTip (tree *tr, nodeptr p)
{ 
  nodeptr  q;

  q = tr->nodep[(tr->nextnode)++];
  hookupDefault(p, q, tr->numBranches);
  q->next->back = (nodeptr)NULL;
  q->next->next->back = (nodeptr)NULL;
  assert(q == q->next->next->next);
  assert(q->x || q->next->x || q->next->next->x);
  return  q;
} 

static void buildSimpleTree (tree *tr, int ip, int iq, int ir)
{    
  nodeptr  p, s;
  int  i;
  
  i = MIN(ip, iq);
  if (ir < i)  i = ir; 
  tr->start = tr->nodep[i];
  tr->ntips = 3;
  p = tr->nodep[ip];
  hookupDefault(p, tr->nodep[iq], tr->numBranches);
  s = buildNewTip(tr, tr->nodep[ir]);
  insertParsimony(tr, s, p);
}


static void buildSimpleTreeRandom (tree *tr, int ip, int iq, int ir)
{    
  nodeptr  p, s;
  int  i;
  
  i = MIN(ip, iq);
  if (ir < i)  i = ir; 
  tr->start = tr->nodep[i];
  tr->ntips = 3;
  p = tr->nodep[ip];
  hookupDefault(p, tr->nodep[iq], tr->numBranches);
  s = buildNewTip(tr, tr->nodep[ir]);
  insertRandom(s, p, tr->numBranches);
}

int checker(tree *tr, nodeptr p)
{
  int group = tr->constraintVector[p->number];

  if(isTip(p->number, tr->mxtips))
    {
      group = tr->constraintVector[p->number];
      return group;
    }
  else
    {
      if(group != -9) 
	return group;

      group = checker(tr, p->next->back);
      if(group != -9) 
	return group;

      group = checker(tr, p->next->next->back);
      if(group != -9) 
	return group;

      return -9;
    }
}


static void testInsertParsimony (tree *tr, nodeptr p, nodeptr q)
{ 
  unsigned int mp;
  boolean doIt = TRUE;
  nodeptr  r = q->back;
 
  if(tr->grouped)
    {
      int rNumber, qNumber, pNumber;

      doIt = FALSE;
     
      rNumber = tr->constraintVector[r->number];
      qNumber = tr->constraintVector[q->number];
      pNumber = tr->constraintVector[p->number];

      if(pNumber == -9)
	pNumber = checker(tr, p->back);
      if(pNumber == -9)
	doIt = TRUE;
      else
	{
	  if(qNumber == -9)
	    qNumber = checker(tr, q);

	  if(rNumber == -9)
	    rNumber = checker(tr, r);

	  if(pNumber == rNumber || pNumber == qNumber)
	    doIt = TRUE;       
	}
    }

  if(doIt)
    {     
      insertParsimony(tr, p, q);   
      mp = evaluateParsimony(tr, p->next->next);          
      
      if(mp < tr->bestParsimony)
	{
	  tr->bestParsimony = mp;
	  tr->insertNode = q;
	  tr->removeNode = p;
	}
      
      hookupDefault(q, r, tr->numBranches);
      p->next->next->back = p->next->back = (nodeptr) NULL;

    }      

  return;
} 


static void restoreTreeParsimony(tree *tr, nodeptr p, nodeptr q)
{ 
  insertParsimony(tr, p, q);  

  if(! isTip(p->number, tr->mxtips) && isTip(q->number, tr->mxtips))
    {
      while ((! p->x)) 
	{
	  if (! (p->x))
	    newviewParsimony(tr, p);		     
	}
    }
  if(isTip(p->number, tr->mxtips) && ! isTip(q->number, tr->mxtips))
    {
      while ((! q->x)) 
	{		  
	  if (! (q->x)) 
	    newviewParsimony(tr, q);
	}
    }
  if(! isTip(p->number, tr->mxtips) && ! isTip(q->number, tr->mxtips))
    {
      while ((! p->x) || (! q->x)) 
	{
	  if (! (p->x))
	    newviewParsimony(tr, p);
	  if (! (q->x))
	    newviewParsimony(tr, q);
	}
    }	
}


static int markBranches(nodeptr *branches, nodeptr p, int *counter, int numsp)
{
  if(isTip(p->number, numsp))
    return 0;
  else
    {
      branches[*counter] = p->next;
      branches[*counter + 1] = p->next->next;
      
      *counter = *counter + 2;
      
      return ((2 + markBranches(branches, p->next->back, counter, numsp) + 
	       markBranches(branches, p->next->next->back, counter, numsp)));
    }
}

static void addTraverseParsimony (tree *tr, nodeptr p, nodeptr q, int mintrav, int maxtrav, boolean doAll)
{        
  if (doAll || (--mintrav <= 0))               
    testInsertParsimony(tr, p, q);	                 

  if ((! isTip(q->number, tr->mxtips)) && ((--maxtrav > 0) || doAll))
    {	      
      addTraverseParsimony(tr, p, q->next->back, mintrav, maxtrav, doAll);	      
      addTraverseParsimony(tr, p, q->next->next->back, mintrav, maxtrav, doAll);              	     
    }
}


nodeptr findAnyTip(nodeptr p, int numsp)
{ 
  return  isTip(p->number, numsp) ? p : findAnyTip(p->next->back, numsp);
} 


int randomInt(int n)
{
  return rand() %n;
}

void makePermutation(int *perm, int n, analdef *adef)
{    
  int  i, j, k;

#ifdef PARALLEL
   srand((unsigned int) gettimeSrand()); 
#else
  if(adef->parsimonySeed == 0)   
    srand((unsigned int) gettimeSrand());          
#endif

  for (i = 1; i <= n; i++)    
    perm[i] = i;               

  for (i = 1; i <= n; i++) 
    {
#ifdef PARALLEL      
      k        = randomInt(n + 1 - i);
#else
     if(adef->parsimonySeed == 0) 
       k        = randomInt(n + 1 - i);
     else
       k =  (int)((double)(n + 1 - i) * randum(&adef->parsimonySeed));
#endif
     assert(i + k <= n);

     j        = perm[i];
     perm[i]     = perm[i + k];
     perm[i + k] = j; 
    }

  /*  for(i = 1; i <= n; i++)
    printf("%d ", perm[i]);
    printf("\n");*/

}

static void initravDISTParsimony (tree *tr, nodeptr p, int distance)
{
  nodeptr  q;

  if (! isTip(p->number, tr->mxtips) && distance > 0) 
    {      
      q = p->next;      
      do 
	{
	  initravDISTParsimony(tr, q->back, --distance);	
	  q = q->next;	
	} 
      while (q != p);
      
      
      newviewParsimony(tr, p);	      
    } 
}


static nodeptr  removeNodeParsimony (nodeptr p, int numBranches)
{ 
  nodeptr  q, r;         

  q = p->next->back;
  r = p->next->next->back;   
    
  hookupDefault(q, r, numBranches);

  p->next->next->back = p->next->back = (node *) NULL;
  
  return  q;
}



boolean tipHomogeneityChecker(tree *tr, nodeptr p, int grouping)
{
  if(isTip(p->number, tr->mxtips))
    {
      if(tr->constraintVector[p->number] != grouping) 
	return FALSE;
      else 
	return TRUE;
    }
  else
    {   
      return  (tipHomogeneityChecker(tr, p->next->back, grouping) && tipHomogeneityChecker(tr, p->next->next->back,grouping));      
    }
}

static int rearrangeParsimony(tree *tr, nodeptr p, int mintrav, int maxtrav, boolean doAll)  
{   
  nodeptr  p1, p2, q, q1, q2;
  int      mintrav2;
  boolean doP = TRUE, doQ = TRUE;
           
  if (maxtrav > tr->ntips - 3)  
    maxtrav = tr->ntips - 3; 

  assert(mintrav == 1);
  if(maxtrav < mintrav)
    return 0;

  q = p->back;

  if(tr->constrained)
    {    
      if(! tipHomogeneityChecker(tr, p->back, 0))
	doP = FALSE;
	
      if(! tipHomogeneityChecker(tr, q->back, 0))
	doQ = FALSE;
		        
      if(doQ == FALSE && doP == FALSE)
	return 0;
    }  

  if (!isTip(p->number, tr->mxtips) && doP) 
    {     
      p1 = p->next->back;
      p2 = p->next->next->back;
      
      if (! isTip(p1->number, tr->mxtips) || ! isTip(p2->number, tr->mxtips)) 
	{	  	  
	  removeNodeParsimony(p, tr->numBranches);
	  
	 

	  if (! isTip(p1->number, tr->mxtips)) 
	    {
	      addTraverseParsimony(tr, p, p1->next->back, mintrav, maxtrav, doAll);         
	      addTraverseParsimony(tr, p, p1->next->next->back, mintrav, maxtrav, doAll);          
	    }
	 
	  if (! isTip(p2->number, tr->mxtips)) 
	    {
	      addTraverseParsimony(tr, p, p2->next->back, mintrav, maxtrav, doAll);
	      addTraverseParsimony(tr, p, p2->next->next->back, mintrav, maxtrav, doAll);          
	    }
	    
	   
	  hookupDefault(p->next,       p1, tr->numBranches); 
	  hookupDefault(p->next->next, p2, tr->numBranches);	   	    	    
	  initravDISTParsimony(tr, p, 1);   
	}
    }  
       
  if (! isTip(q->number, tr->mxtips) && maxtrav > 0 && doQ) 
    {
      q1 = q->next->back;
      q2 = q->next->next->back;

      if (
	  (
	   ! isTip(q1->number, tr->mxtips) && 
	   (! isTip(q1->next->back->number, tr->mxtips) || ! isTip(q1->next->next->back->number, tr->mxtips))
	   )
	  ||
	  (
	   ! isTip(q2->number, tr->mxtips) && 
	   (! isTip(q2->next->back->number, tr->mxtips) || ! isTip(q2->next->next->back->number, tr->mxtips))
	   )
	  )
	{	   

	  removeNodeParsimony(q, tr->numBranches);
	  
	  mintrav2 = mintrav > 2 ? mintrav : 2;
	  
	  if (! isTip(q1->number, tr->mxtips)) 
	    {
	      addTraverseParsimony(tr, q, q1->next->back, mintrav2 , maxtrav, doAll);
	      addTraverseParsimony(tr, q, q1->next->next->back, mintrav2 , maxtrav, doAll);         
	    }
	 
	  if (! isTip(q2->number, tr->mxtips)) 
	    {
	      addTraverseParsimony(tr, q, q2->next->back, mintrav2 , maxtrav, doAll);
	      addTraverseParsimony(tr, q, q2->next->next->back, mintrav2 , maxtrav, doAll);          
	    }	   
	   
	  hookupDefault(q->next,       q1, tr->numBranches); 
	  hookupDefault(q->next->next, q2, tr->numBranches);
	   
	  initravDISTParsimony(tr, q, 1); 	   
	}
    }

  return 1;
} 


static void restoreTreeRearrangeParsimony(tree *tr)
{    
  removeNodeParsimony(tr->removeNode, tr->numBranches);  
  restoreTreeParsimony(tr, tr->removeNode, tr->insertNode);  
}






#ifdef WIN32
static void switchTipEntries(int number, int position1, int position2, 
			     char *y0, int originalCrunchedLength, int numsp)
#else
static inline void switchTipEntries(int number, int position1, int position2, 
				    char *y0, int originalCrunchedLength, int numsp)
#endif
{
  char buf;
  char *ref = &y0[originalCrunchedLength * (number - 1)];

  assert(number <= numsp && number > 0);
  assert(position1 <  originalCrunchedLength && position2 < originalCrunchedLength);
  assert(position1 >= 0 && position2 >= 0);

  buf = ref[position1];
  ref[position1] = ref[position2];
  ref[position2] = buf;
}





static void sortInformativeSites(tree *tr, int *informative)
{
  int i, l, j;

  for(i = 0; i < tr->mxtips; i++)
    {
      unsigned char *yPos    = &(tr->rdta->y0[tr->originalCrunchedLength * i]);        
      
      for(j = 0, l = 0; j < tr->cdta->endsite; j++)
	{	
	  if(informative[j])	  
	    {	     
	      yPos[l++] = yPos[j];
	    }
	}               
    }
    
  for(j = 0, l = 0; j < tr->cdta->endsite; j++)
    {     
      if(informative[j])	
	{
	  tr->cdta->aliaswgt[l]     = tr->cdta->aliaswgt[j];	
	  tr->model[l]              = tr->model[j];	 
	  tr->dataVector[l]           = tr->dataVector[j];
	  l++;
	}
    }    
}

/* TODO should re-visit this one day, not sure that I am getting all uninformative sites */

static void determineUninformativeSites(tree *tr, int *informative)
{
  int i, j;
  int check[256];
  int nucleotide;
  int informativeCounter;       
  int number = 0;

  /* 
     Not all characters are useful in constructing a parsimony tree. 
     Invariant characters, those that have the same state in all taxa, 
     are obviously useless and are ignored by the method. Characters in 
     which a state occurs in only one taxon are also ignored. 
     All these characters are called parsimony uninformative.
  */

  for(i = 0; i < tr->cdta->endsite; i++)
    {
      switch(tr->dataVector[i])
	{
	case SECONDARY_DATA:
	  for(j = 0; j < 256; j++)
	    check[j] = 0;
	  
	  for(j = 1; j <= tr->mxtips; j++)
	    {	   
	      nucleotide = tr->yVector[tr->nodep[j]->number][i];	    
	      check[nucleotide] =  check[nucleotide] + 1;
	      assert(bitVectorSecondary[nucleotide] > 0);	     
	      assert(nucleotide < 256 && nucleotide > 0);
	    }
	  
	  informativeCounter = 0;
	  
	  for(j = 1; j < 255; j++)
	    {
	      if(check[j] > 0)
		informativeCounter++;    
	    } 
	  
	  if(informativeCounter <= 1)
	    {
	      informative[i] = 0;
	      number++;
	    }
	  else
	    {
	      boolean isInformative = FALSE;
	      for(j = 1; j < 255 && !(isInformative); j++)
		{
		  if(check[j] > 1)
		    isInformative = TRUE;
		} 

	      if(isInformative)
		informative[i] = 1; 
	      else
		{
		  informative[i] = 0; 
		  number++;
		}	  
	    }           	 	 
	  break;
	case SECONDARY_DATA_6:
	  for(j = 0; j < 64; j++)
	    check[j] = 0;
	  
	  for(j = 1; j <= tr->mxtips; j++)
	    {	   
	      nucleotide = tr->yVector[tr->nodep[j]->number][i];	    
	      check[nucleotide] =  check[nucleotide] + 1;
	      assert(nucleotide > 0);
	      assert(nucleotide < 64 && nucleotide > 0);
	    }
	  
	  informativeCounter = 0;
	  
	  for(j = 1; j < 63; j++)
	    {
	      if(check[j] > 0)
		informativeCounter++;    
	    } 
	  
	  if(informativeCounter <= 1)
	    {
	      informative[i] = 0;
	      number++;
	    }
	  else
	    {
	      boolean isInformative = FALSE;
	      for(j = 1; j < 63 && !(isInformative); j++)
		{
		  if(check[j] > 1)
		    isInformative = TRUE;
		} 

	      if(isInformative)
		informative[i] = 1; 
	      else
		{
		  informative[i] = 0; 
		  number++;
		}	  
	    }           	 	 
	  break;
	case SECONDARY_DATA_7:
	  for(j = 0; j < 128; j++)
	    check[j] = 0;
	  
	  for(j = 1; j <= tr->mxtips; j++)
	    {	   
	      nucleotide = tr->yVector[tr->nodep[j]->number][i];	    
	      check[nucleotide] =  check[nucleotide] + 1;
	      assert(nucleotide > 0);
	      assert(nucleotide < 128 && nucleotide > 0);
	    }
	  
	  informativeCounter = 0;
	  
	  for(j = 1; j < 127; j++)
	    {
	      if(check[j] > 0)
		informativeCounter++;    
	    } 
	  
	  if(informativeCounter <= 1)
	    {
	      informative[i] = 0;
	      number++;
	    }
	  else
	    {
	      boolean isInformative = FALSE;
	      for(j = 1; j < 127 && !(isInformative); j++)
		{
		  if(check[j] > 1)
		    isInformative = TRUE;
		} 

	      if(isInformative)
		informative[i] = 1; 
	      else
		{
		  informative[i] = 0; 
		  number++;
		}	  
	    }           	 	 
	  break;  
	case AA_DATA: 
	  for(j = 0; j < 23; j++)
	    check[j] = 0;
	  
	  for(j = 1; j <= tr->mxtips; j++)
	    {	     
	      nucleotide = tr->yVector[tr->nodep[j]->number][i];	      
	      check[nucleotide] = check[nucleotide] + 1;
	      assert(nucleotide < 23 && nucleotide >= 0);
	    }
	  
	  informativeCounter = 0;
	  
	  for(j = 0; j < 22; j++)
	    {
	      if(check[j] > 0)
		informativeCounter++;    
	    } 
	  
	  if(informativeCounter <= 1)
	    {
	      informative[i] = 0;
	      number++;
	    }
	  else
	    {
	      boolean isInformative = FALSE;
	      for(j = 0; j < 22 && !(isInformative); j++)
		{
		  if(check[j] > 1)
		    isInformative = TRUE;
		} 

	      if(isInformative)
		informative[i] = 1; 
	      else
		{
		  informative[i] = 0; 
		  number++;
		}	  
	    }           
	  break;
	case DNA_DATA:     
	  for(j = 1; j < 16; j++)
	    check[j] = 0;
	  
	  for(j = 1; j <= tr->mxtips; j++)
	    {	   
	      nucleotide = tr->yVector[tr->nodep[j]->number][i];	    
	      check[nucleotide] =  check[nucleotide] + 1;
	      assert(nucleotide < 16 && nucleotide >= 0);
	    }
	  
	  informativeCounter = 0;
	  
	  for(j = 1; j < 15; j++)
	    {
	      if(check[j] > 0)
		informativeCounter++;    
	    } 
	  
	  if(informativeCounter <= 1)
	    {
	      informative[i] = 0;
	      number++;
	    }
	  else
	    {
	      boolean isInformative = FALSE;
	      for(j = 1; j < 15 && !(isInformative); j++)
		{
		  if(check[j] > 1)
		    isInformative = TRUE;
		} 

	      if(isInformative)
		informative[i] = 1; 
	      else
		{
		  informative[i] = 0; 
		  number++;
		}	  
	    }           	 
	  break;
	case BINARY_DATA:
	   for(j = 1; j < 4; j++)
	    check[j] = 0;
	  
	  for(j = 1; j <= tr->mxtips; j++)
	    {	   
	      nucleotide = tr->yVector[tr->nodep[j]->number][i];	    
	      check[nucleotide] =  check[nucleotide] + 1;
	      assert(nucleotide < 4 && nucleotide > 0);
	    }
	  
	  informativeCounter = 0;
	  
	  for(j = 1; j < 4; j++)
	    {
	      if(check[j] > 0)
		informativeCounter++;    
	    } 
	  
	  if(informativeCounter <= 1)
	    {
	      informative[i] = 0;
	      number++;
	    }
	  else
	    {
	      boolean isInformative = FALSE;
	      for(j = 1; j < 4 && !(isInformative); j++)
		{
		  if(check[j] > 1)
		    isInformative = TRUE;
		} 

	      if(isInformative)
		informative[i] = 1; 
	      else
		{
		  informative[i] = 0; 
		  number++;
		}	  
	    }           	 
	  break;
	default:
	  assert(0);
	}
    }
 
  sortInformativeSites(tr, informative);

  /*printf("Uninformative Patterns: %d\n", number);*/
  
  tr->parsimonyLength = tr->cdta->endsite - number;
}



void makeRandomTree(tree *tr, analdef *adef)
{  
  nodeptr p, f, randomBranch;    
  int nextsp;
  int *perm, branchCounter;
  nodeptr *branches;
  
  branches = (nodeptr *)malloc(sizeof(nodeptr) * (2 * tr->mxtips));
  perm = (int *)malloc((tr->mxtips + 1) * sizeof(int));                         
  
  makePermutation(perm, tr->mxtips, adef);              
  
  tr->ntips = 0;       	       
  tr->nextnode = tr->mxtips + 1;    
  
  buildSimpleTreeRandom(tr, perm[1], perm[2], perm[3]);
  
  while (tr->ntips < tr->mxtips) 
    {	       
      tr->bestParsimony = INT_MAX;
      nextsp = ++(tr->ntips);             
      p = tr->nodep[perm[nextsp]];
      
      /*printf("ADDING SPECIES %d\n", nextsp);*/
      
      buildNewTip(tr, p);  	
      
      f = findAnyTip(tr->start, tr->mxtips);
      f = f->back;
      
      branchCounter = 1;
      branches[0] = f;
      markBranches(branches, f, &branchCounter, tr->mxtips);

      assert(branchCounter == ((2 * (tr->ntips - 1)) - 3));
      
      randomBranch = branches[randomInt(branchCounter)];
      
      insertRandom(p->back, randomBranch, tr->numBranches);
      
    }
  free(perm);            
  free(branches);
}


static void reorderNodes(tree *tr, nodeptr *np, nodeptr p, int *count)
{
  int i, found = 0;

  if(isTip(p->number, tr->mxtips))    
    return;
  else
    {              
      for(i = tr->mxtips + 1; (i <= (tr->mxtips + tr->mxtips - 1)) && (found == 0); i++)
	{
	  if (p == np[i] || p == np[i]->next || p == np[i]->next->next)
	    {
	      if(p == np[i])			       
		tr->nodep[*count + tr->mxtips + 1] = np[i];		 		
	      else
		{
		  if(p == np[i]->next)		  
		    tr->nodep[*count + tr->mxtips + 1] = np[i]->next;		     	   
		  else		   
		    tr->nodep[*count + tr->mxtips + 1] = np[i]->next->next;		    		    
		}

	      found = 1;	      	     
	      *count = *count + 1;
	    }
	} 
      
      assert(found != 0);
     
      reorderNodes(tr, np, p->next->back, count);     
      reorderNodes(tr, np, p->next->next->back, count);                
    }
}

void nodeRectifier(tree *tr)
{
  nodeptr *np = (nodeptr *)malloc(2 * tr->mxtips * sizeof(nodeptr));
  int i;
  int count = 0;
  
  tr->start       = tr->nodep[1];
  tr->rooted      = FALSE;

  /* TODO why is tr->rooted set to FALSE here ?*/
  
  for(i = tr->mxtips + 1; i <= (tr->mxtips + tr->mxtips - 1); i++)
    np[i] = tr->nodep[i];           
  
  reorderNodes(tr, np, tr->start->back, &count); 

 
  free(np);
}


void makeParsimonyTree(tree *tr, analdef *adef)
{   
  nodeptr  p, f;    
  int  i, nextsp;
  unsigned int randomMP, startMP;
  int *perm, *informative, *aliaswgt, *model, *dataVector;
  char *parsimonyBuffer;     

  /* stuff for informative sites */

  informative = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  
  aliaswgt    = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(aliaswgt, tr->cdta->aliaswgt, sizeof(int) * tr->cdta->endsite);

  model       = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(model, tr->model, sizeof(int) * tr->cdta->endsite);

  dataVector    = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(dataVector, tr->dataVector, sizeof(int) * tr->cdta->endsite);
  
  parsimonyBuffer = (char *)malloc(tr->originalCrunchedLength * tr->mxtips * sizeof(char));
  memcpy(parsimonyBuffer, tr->rdta->y0, tr->originalCrunchedLength * tr->mxtips * sizeof(char)); 
  
  /* end */

  perm = (int *)malloc((tr->mxtips + 1) * sizeof(int));  
  
  determineUninformativeSites(tr, informative);    

  fixModelIndices(tr, tr->parsimonyLength); 

  makePermutation(perm, tr->mxtips, adef);
  
 
  
  tr->ntips = 0;    
  
  tr->nextnode = tr->mxtips + 1;       
  buildSimpleTree(tr, perm[1], perm[2], perm[3]);      

  while (tr->ntips < tr->mxtips) 
    {	
      tr->bestParsimony = INT_MAX;
      nextsp = ++(tr->ntips);             
      p = tr->nodep[perm[nextsp]];
      
      /*printf("ADDING SPECIES %d\n", p->number);*/
      
      buildNewTip(tr, p);
      
      f = findAnyTip(tr->start, tr->mxtips);
      f = f->back;
      addTraverseParsimony(tr, p->back, f, 1, tr->ntips - 2, FALSE);               	 	
      restoreTreeParsimony(tr, p->back, tr->insertNode);		      
      
      /*printf("MP %d\n", tr->bestParsimony);*/
      
      assert(INT_MAX - tr->bestParsimony >= 1000);	  
    }    
 
  free(perm);    
  
  nodeRectifier(tr);   
  initravParsimonyNormal(tr, tr->start);
  initravParsimonyNormal(tr, tr->start->back);               
  
  randomMP = tr->bestParsimony;        
  
  do
    {
      startMP = randomMP;
      nodeRectifier(tr);
      for(i = 1; i <= tr->mxtips + tr->mxtips - 2; i++)
	{
	  rearrangeParsimony(tr, tr->nodep[i], 1, 20, FALSE);
	  if(tr->bestParsimony < randomMP)
	    {		
	      restoreTreeRearrangeParsimony(tr);
	      randomMP = tr->bestParsimony;
	    }
	}      		  	   

      /*printf("Score %d %d\n", randomMP, startMP);*/
    }
  while(randomMP < startMP);
      
  /*printf("REARRANGEMENT MP Score %d Time %f\n", tr->bestParsimony, gettime() - masterTime);*/
  
 
  nodeRectifier(tr);       
    
  /* repair */
  
  memcpy(tr->cdta->aliaswgt, aliaswgt, sizeof(int) * tr->cdta->endsite);

  memcpy(tr->model,    model   , sizeof(int) * tr->cdta->endsite);
 
  memcpy(tr->dataVector, dataVector, sizeof(int) * tr->cdta->endsite);
  
  memcpy(tr->rdta->y0, parsimonyBuffer, tr->originalCrunchedLength * tr->mxtips * sizeof(char));

  fixModelIndices(tr, tr->cdta->endsite);

  /* repair end */  

  free(informative);    
  free(parsimonyBuffer);
  free(model);
  free(dataVector);
  free(aliaswgt);
} 

void makeParsimonyTreeRapid(tree *tr, analdef *adef)
{   
  nodeptr  p, f;    
  int  i, nextsp;
  unsigned int randomMP, startMP;
  int *perm, *informative, *aliaswgt, *model, *dataVector;
  char *parsimonyBuffer;     

  /* stuff for informative sites */

  informative = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  
  aliaswgt    = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(aliaswgt, tr->cdta->aliaswgt, sizeof(int) * tr->cdta->endsite);

  model       = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(model, tr->model, sizeof(int) * tr->cdta->endsite);

  dataVector    = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(dataVector, tr->dataVector, sizeof(int) * tr->cdta->endsite);
  
  parsimonyBuffer = (char *)malloc(tr->originalCrunchedLength * tr->mxtips * sizeof(char));
  memcpy(parsimonyBuffer, tr->rdta->y0, tr->originalCrunchedLength * tr->mxtips * sizeof(char)); 
  
  /* end */

  perm = (int *)malloc((tr->mxtips + 1) * sizeof(int));  
  
  determineUninformativeSites(tr, informative);    

  fixModelIndices(tr, tr->parsimonyLength); 

  makePermutation(perm, tr->mxtips, adef);
     
  tr->ntips = 0;    
  
  tr->nextnode = tr->mxtips + 1;       
  buildSimpleTree(tr, perm[1], perm[2], perm[3]);      

  while (tr->ntips < tr->mxtips) 
    {	
      tr->bestParsimony = INT_MAX;
      nextsp = ++(tr->ntips);             
      p = tr->nodep[perm[nextsp]];
      
      /*printf("ADDING SPECIES %d\n", p->number); */
      
      buildNewTip(tr, p);
      
      f = findAnyTip(tr->start, tr->mxtips);
      f = f->back;
      addTraverseParsimony(tr, p->back, f, 1, tr->ntips - 2, FALSE);               	 	
      restoreTreeParsimony(tr, p->back, tr->insertNode);		      
      
      /*printf("MP %d\n", tr->bestParsimony);*/
      
      assert(INT_MAX - tr->bestParsimony >= 1000);	  
    }    
 
  free(perm);    
  
 
  
 
  nodeRectifier(tr);       
    
  /* repair */
  
  memcpy(tr->cdta->aliaswgt, aliaswgt, sizeof(int) * tr->cdta->endsite);

  memcpy(tr->model,    model   , sizeof(int) * tr->cdta->endsite);
 
  memcpy(tr->dataVector, dataVector, sizeof(int) * tr->cdta->endsite);
  
  memcpy(tr->rdta->y0, parsimonyBuffer, tr->originalCrunchedLength * tr->mxtips * sizeof(char));

  fixModelIndices(tr, tr->cdta->endsite);



  /* repair end */  

 


  free(informative);    
  free(parsimonyBuffer);
  free(model);
  free(dataVector);
  free(aliaswgt);
} 
 

void makeParsimonyTreeIncomplete(tree *tr, analdef *adef)
{   
  nodeptr  p, f;    
  int  i, j, k, nextsp;
  unsigned int randomMP, startMP;
  int *perm, *informative, *aliaswgt, *model, *dataVector;
  char *parsimonyBuffer;     

  /* stuff for informative sites */  

 

  informative = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  
  aliaswgt    = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(aliaswgt, tr->cdta->aliaswgt, sizeof(int) * tr->cdta->endsite);

  model       = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(model, tr->model, sizeof(int) * tr->cdta->endsite);

  dataVector    = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(dataVector, tr->dataVector, sizeof(int) * tr->cdta->endsite);


  parsimonyBuffer = (char *)malloc(tr->originalCrunchedLength * tr->mxtips * sizeof(char));
  memcpy(parsimonyBuffer, tr->rdta->y0, tr->originalCrunchedLength * tr->mxtips * sizeof(char)); 
  

  /* end */

  perm = (int *)malloc((tr->mxtips + 1) * sizeof(int));

  /*for(i = 1; i <= 2 * tr->mxtips; i++)
    printf("%d %d\n", i, tr->constraintVector[i]);*/



  if(!tr->grouped)
    {     
      for(i = 1; i <= tr->mxtips; i++)
	tr->constraintVector[i] = 0;
    }  

  determineUninformativeSites(tr, informative);

  fixModelIndices(tr, tr->parsimonyLength); 
 
  if(!tr->grouped)
    {
      initravParsimony(tr, tr->start,       tr->constraintVector);
      initravParsimony(tr, tr->start->back, tr->constraintVector);
    }
  else
    {
      initravParsimonyNormal(tr, tr->start);
      initravParsimonyNormal(tr, tr->start->back);      
    }   

  /*printf("Incomplete Parsimony score %d\n", evaluateParsimony(tr, tr->start));*/

  j = tr->ntips + 1;
  if(!tr->grouped)
    {
      for(i = 1; i <= tr->mxtips; i++)      
	if(tr->constraintVector[i] == 0) 
	  perm[j++] = i;	    	  
    }
  else
    {
      for(i = 1; i <= tr->mxtips; i++)      
	{
	  if(tr->constraintVector[i] == -1) 
	    {
	      perm[j++] = i;		
	      tr->constraintVector[i] = -9;
	    }
	}
    }
     
#ifdef PARALLEL
  srand((unsigned int) gettimeSrand()); 
#else
  if(adef->parsimonySeed == 0)   
    srand((unsigned int) gettimeSrand());         
#endif

  for (i = tr->ntips + 1; i <= tr->mxtips; i++) 
    {
#ifdef PARALLEL         
      k        = randomInt(tr->mxtips + 1 - i);
#else
      if(adef->parsimonySeed == 0) 
	k        = randomInt(tr->mxtips + 1 - i);
      else
	k =  (int)((double)(tr->mxtips + 1 - i) * randum(&adef->parsimonySeed));
#endif
      assert(i + k <= tr->mxtips);
      j        = perm[i];
      perm[i]     = perm[i + k];
      perm[i + k] = j; 
    }             
 
#ifdef DEBUG_CONSTRAINTS        
  for(i = 1; i <= tr->mxtips; i++)     
    printf("TIP %s %d\n", tr->nameList[i], tr->constraintVector[i]);              
#endif

  while (tr->ntips < tr->mxtips) 
    {	
      tr->bestParsimony = INT_MAX;
      nextsp = ++(tr->ntips);     
      assert(nextsp < 2 * tr->mxtips);
      p = tr->nodep[perm[nextsp]];
      
      /*printf("ADDING SPECIES %d %s\n", perm[nextsp], tr->nameList[perm[nextsp]]);*/

      buildNewTip(tr, p);      
       
      /*      printf("K2 %d %d %d %d\n", tr->start->number, tr->start->back->number, p->number, p->back->number);*/

      if(tr->grouped)
	{
	  int number = p->back->number;
	  tr->constraintVector[number] = -9;
	}      

      /* shouldn't that be ntips? */

      f = findAnyTip(tr->start, tr->mxtips);
      f = f->back;      

      /*printf("K4 %d %d\n", f->number, f->back->number);*/
      assert(isTip(f->back->number, tr->mxtips));
      if(tr->grouped)
	{
	  tr->grouped = FALSE;
	  addTraverseParsimony(tr, p->back, f, 1, tr->ntips - 2, FALSE);  
	  tr->grouped = TRUE;
	}
      else
	{
	  /*printf("K4a\n");*/
	  addTraverseParsimony(tr, p->back, f, 1, tr->ntips - 2, FALSE);
	}
      /*printf("K5\n");*/

      restoreTreeParsimony(tr, p->back, tr->insertNode);		      
      
      /*printf("K6\n");*/

      assert(INT_MAX - tr->bestParsimony >= 1000);	 
    }               
 
  free(perm);
  
  /*printf("RANDOM ADDITION MP Score %d Time %f\n", tr->bestParsimony, gettime() - masterTime); */
  /*printf("K7\n");*/
  nodeRectifier(tr);   
  initravParsimonyNormal(tr, tr->start);
  initravParsimonyNormal(tr, tr->start->back); 

  /*printf("K8\n");*/

  if(adef->mode != PARSIMONY_ADDITION)
    {
      randomMP = tr->bestParsimony;        
      
      do
	{
	  startMP = randomMP;
	  nodeRectifier(tr);
	  for(i = 1; i <= tr->mxtips + tr->mxtips - 2; i++)
	    {		
	      if(rearrangeParsimony(tr, tr->nodep[i], 1, 20, FALSE))
		{
		  if(tr->bestParsimony < randomMP)
		    {		
		      restoreTreeRearrangeParsimony(tr);
		      randomMP = tr->bestParsimony;
		    }				
		}		    		     		 
	    }   
	}
      while(randomMP < startMP);
      
      /*printf("REARRANGEMENT MP Score %d Time %f\n", tr->bestParsimony, gettime() - masterTime);*/
    }
  else
    {               
      return;
    }
  /*printf("K9\n")*/

  nodeRectifier(tr);  
  
   /* repair */
  
  memcpy(tr->cdta->aliaswgt, aliaswgt, sizeof(int) * tr->cdta->endsite);

  memcpy(tr->model,    model   , sizeof(int) * tr->cdta->endsite);
 
  memcpy(tr->dataVector, dataVector, sizeof(int) * tr->cdta->endsite);
  
  memcpy(tr->rdta->y0, parsimonyBuffer, tr->originalCrunchedLength * tr->mxtips * sizeof(char));

  fixModelIndices(tr, tr->cdta->endsite);

  /* repair end */  
  free(informative);    
  free(parsimonyBuffer);
  free(model);
  free(dataVector);
  free(aliaswgt); 

  /*printf("K10\n");*/
   
} 


/* thorough for MRP */


void makeParsimonyTreeThorough(tree *tr, analdef *adef)
{   
  nodeptr  
    p, 
    f;    

  int  
    i, 
    nextsp, 
    k, 
    *perm, 
    *informative, 
    *aliaswgt, 
    *model, 
    *dataVector,
    *origWeights;    
  
  unsigned int
    bestMP,
    startMP,   
    overallBestMP;
 
  char 
    *parsimonyBuffer; 

  double 
    limit;

  topolRELL_LIST 
    *rl = (topolRELL_LIST *)malloc(sizeof(topolRELL_LIST));

  FILE *outf;

  long 
    ratchetSeed;

  if(adef->parsimonySeed == 0)   
    ratchetSeed = 12345;  
  else
    ratchetSeed = adef->parsimonySeed;

  initTL(rl, tr, 1);

  /* stuff for informative sites */

  informative = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  
  aliaswgt    = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(aliaswgt, tr->cdta->aliaswgt, sizeof(int) * tr->cdta->endsite);

  model       = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(model, tr->model, sizeof(int) * tr->cdta->endsite);

  dataVector    = (int *)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(dataVector, tr->dataVector, sizeof(int) * tr->cdta->endsite);
  
  parsimonyBuffer = (char *)malloc(tr->originalCrunchedLength * tr->mxtips * sizeof(char));
  memcpy(parsimonyBuffer, tr->rdta->y0, tr->originalCrunchedLength * tr->mxtips * sizeof(char)); 
  
  /* end */

  perm = (int *)malloc((tr->mxtips + 1) * sizeof(int));  
  
  determineUninformativeSites(tr, informative);    

  fixModelIndices(tr, tr->parsimonyLength); 

  makePermutation(perm, tr->mxtips, adef);
     
  tr->ntips = 0;    
  
  tr->nextnode = tr->mxtips + 1;       
  buildSimpleTree(tr, perm[1], perm[2], perm[3]);      

  while (tr->ntips < tr->mxtips) 
    {	
      tr->bestParsimony = INT_MAX;
      nextsp = ++(tr->ntips);             
      p = tr->nodep[perm[nextsp]];            
      
      buildNewTip(tr, p);
      
      f = findAnyTip(tr->start, tr->mxtips);
      f = f->back;
      addTraverseParsimony(tr, p->back, f, 1, tr->ntips - 2, TRUE);               	 	
      restoreTreeParsimony(tr, p->back, tr->insertNode);		            
      
      assert(INT_MAX - tr->bestParsimony >= 1000);	  
    }    
 
  free(perm);   
 
  printBothOpen("\n\nStepwise Addition Parsimony Score %d\n\n", tr->bestParsimony);         
  
  printBothOpen("\n\nExecuting %d Parsimony Ratchets\n\n", adef->multipleRuns);

  origWeights = (int*)malloc(sizeof(int) * tr->cdta->endsite);
  memcpy(origWeights, tr->cdta->aliaswgt, tr->cdta->endsite * sizeof(int));
  
  nodeRectifier(tr);
  initravParsimonyNormal(tr, tr->start);
  initravParsimonyNormal(tr, tr->start->back);
  overallBestMP = evaluateParsimony(tr, tr->start);

  for(k = 0; k < adef->multipleRuns; k++)
    {	
      double ratchetTime = gettime();         
      
      nodeRectifier(tr);   
      initravParsimonyNormal(tr, tr->start);
      initravParsimonyNormal(tr, tr->start->back);               
      bestMP = evaluateParsimony(tr, tr->start);
  
      if(k == 0)
	assert(bestMP == overallBestMP);
   
      do
	{
	  startMP = bestMP;
	  tr->bestParsimony = INT_MAX;
	  
	  nodeRectifier(tr);

	  for(i = 1; i <= tr->mxtips + tr->mxtips - 2; i++)
	    {
	      /*if(k > 0)*/
	      /*rearrangeParsimony(tr, tr->nodep[i], 1, 5, FALSE);*/
	      /*  else*/
	      rearrangeParsimony(tr, tr->nodep[i], 1, 10, TRUE);
	      if(tr->bestParsimony < bestMP)
		{		
		  restoreTreeRearrangeParsimony(tr);
		  bestMP = tr->bestParsimony;		    
		}
	    }      		  	
	  if(k > 0)
	    break;		  
	}
      while(bestMP < startMP);
      
      if(k == 0)
	assert(bestMP == startMP);
      else
	assert(bestMP <= startMP);

      if(bestMP < overallBestMP)
	{
	  rl->t[0]->likelihood = -2.0;  
	  tr->likelihood = -1.0;	 
	  saveTL(rl, tr, 0);	 
	  overallBestMP = bestMP;           
	}
            	
      limit = 0.5 * randum(&ratchetSeed);

      for(i = 0; i < tr->cdta->endsite; i++)
	{
	  double r = randum(&ratchetSeed);
	  assert(0 <= r && r < 1.0);
	  if(r < 0.5)
	    tr->cdta->aliaswgt[i] =  tr->cdta->aliaswgt[i] + 1;
	}

#ifdef _USE_PTHREADS
      masterBarrier(THREAD_PARSIMONY_RATCHET, tr);
#endif

      initravParsimonyNormal(tr, tr->start);
      initravParsimonyNormal(tr, tr->start->back);
      bestMP = evaluateParsimony(tr, tr->start);
       
      tr->bestParsimony = INT_MAX;	
      nodeRectifier(tr);
      for(i = 1; i <= tr->mxtips + tr->mxtips - 2; i++)
	{
	  rearrangeParsimony(tr, tr->nodep[i], 1, 10, TRUE);
	  /*rearrangeParsimony(tr, tr->nodep[i], 1, 5, FALSE);*/
	  if(tr->bestParsimony < bestMP)
	    {				
	      restoreTreeRearrangeParsimony(tr);
	      bestMP = tr->bestParsimony;
	    }
	}           
	
      memcpy(tr->cdta->aliaswgt, origWeights, tr->cdta->endsite * sizeof(int)); 
    
#ifdef _USE_PTHREADS 
      masterBarrier(THREAD_PARSIMONY_RATCHET, tr);
#endif

      printBothOpen("Ratchet [%d] finished in %f seconds, current best parsimony score: %d\n", k, gettime() - ratchetTime, overallBestMP);
  }
  
  restoreTL(rl, tr, 0);  
  initravParsimonyNormal(tr, tr->start);
  initravParsimonyNormal(tr, tr->start->back);
  bestMP = evaluateParsimony(tr, tr->start);

  assert(bestMP == overallBestMP);

  Tree2String(tr->tree_string, tr, tr->start->back, FALSE, TRUE, FALSE, FALSE, TRUE, adef, NO_BRANCHES);
  
  outf = myfopen(permFileName, "w");
  fprintf(outf, "%s", tr->tree_string);
  fclose(outf);

  printBothOpen("\n\nBest-scoring Parsimony tree with score %d written to file %s\n\n", overallBestMP, permFileName);


  printBothOpen("Overall execution time for %d ratchet searches: %f\n\n", adef->multipleRuns, gettime() - masterTime);
  
  printBothOpen("Execution information file written to file: %s\n\n", infoFileName);


  exit(0);  
} 
