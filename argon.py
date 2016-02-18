import math
import numpy
import scipy.stats
import random
import time
import matplotlib.pyplot as plt
from numba import jit
numpy.set_printoptions(threshold=numpy.nan)


def mainf(T, rho, num_particles, n_iter, n_iter_init, dt, bin_count, bin_size, rcut, rrms, n_iter_cut):


    L = (num_particles/rho)**(1/3)
    n_t = 1
    print('L= ',L)

    def print_particles(x, v, a):
        for i in range(0, num_particles):
            print("particle ",i,": x:",x[:,i]," v:",v[:,i]," a:",a[:,i])


    def initial_positions(N): #position function of particles
        if (N != 4 and N != 32 and N != 108 and N != 256 and N!= 500 and N != 864):
            print("The value entered for N amount of particles is invalid")
            exit()
        
        Ncel = round((N/4)**(1/3)) #The amount of primitive cells to produce the amount of particles 
        print("Ncel=",Ncel)
        aceltot = numpy.zeros(shape=(3,N), dtype="float64") #The matrix that will contain all the position of the particles

        acel = numpy.array([[0,0,0.5,0.5],[0,0.5,0,0.5],[0,0.5,0.5,0]]) #Primitive cel matrix   

        ax = numpy.array([[1,1,1,1],[0,0,0,0],[0,0,0,0]])
        ay = numpy.array([[0,0,0,0],[1,1,1,1],[0,0,0,0]])
        az = numpy.array([[0,0,0,0],[0,0,0,0],[1,1,1,1]])

        offs = 0
        for m in range(Ncel):
            for k in range(Ncel):
                for l in range(Ncel):
                    aceltot[:,offs:offs+4] = acel + l*ax + k*ay + m*az
                    offs += 4
        aceltot = aceltot*L/Ncel - L/2

        return(aceltot)

    def initial_velocities(N,T):
        v = numpy.zeros([3,N])
        # maxwell (normal) distribution
        v[0,:] = numpy.random.normal(size=N)
        v[1,:] = numpy.random.normal(size=N)
        v[2,:] = numpy.random.normal(size=N)
        v *= math.sqrt(T)
        # set total momentum to zero
        v_mean = numpy.mean(v,1)
        for i in range(0,N):
            v[:,i] -= v_mean
        return v

    def initial_accelerations(N):
        a = numpy.zeros([3,N])
        return a

    @jit
    def lennard_jones(r):
        r2 = numpy.sum(r*r)
        r6 = r2*r2*r2
        r8 = r6*r2
        r12 = r6*r6
        r14 = r8*r6
        Fij = r * 4 * ( 12*(1/r14) -6*(1/r8) )
        Vij = 4 * ( (1/r12) - (1/r6) )
        return Fij, Vij

    def lennard_jones_force_length(r):
        return 4 * ( 12*(1/r**13) - 6*(1/r**7) )

    @jit
    def closest_image_distance(xi,xj,L):
        # find which image particle is closest
        c = numpy.rint((xi-xj) / L)
        xj_mirror = xj + c*L
        r = xi-xj_mirror
        return r

    @jit
    def all_distance(x, N, L, rcut, rrms):
        rmax = rcut + rrms
        r_dis = numpy.zeros((N,N))
        
        for i in range(0, N):
            for j in range(i+1, N):
                r = closest_image_distance(x[:,i],x[:,j],L)
                rij = numpy.sqrt(numpy.sum(r*r))

                if rij < rmax:
                    r_dis[i,j] += 1
                    r_dis[j,i] += 1

        return r_dis
                
    @jit
    def update_cut(N, L, x, v, a, dt, n_t, r_all):
        Vtot = 0
        Ktot = 0

        v += 0.5*a*dt
        dx = v*dt
        x += dx
        a = numpy.zeros(shape=(3,N))

        for i in range(0, N):
            k = numpy.nonzero(r_all[i,:])
            m = k[0]
            l = len(k[0])
            for j in range(0,l):
                f = int(m[j])
                r = closest_image_distance(x[:,i],x[:,f],L)
                # calculate force, potential
                Fij, Vij = lennard_jones(r)
                a[:,i] += Fij
                Vtot += Vij/2

        v += 0.5*a*dt

        # make sure the particles stay in the box
        for i in range(0, N):
            c = numpy.rint(x[:,i]/L)
            x[:,i] -= c*L
            #calculate kinetic energy
            Ktot += 0.5*numpy.sum(v[:,i]*v[:,i])

        Etot = Vtot + Ktot
        v_sum = numpy.sum(v,1)

        return x,v,a,Vtot,Ktot,Etot,v_sum,dx

    #@jit
    def update(N, L, x, v, a, dt, n_t):
        Vtot = 0
        Ktot = 0

        v += 0.5*a*dt
        dx = v*dt
        x += dx
        a = numpy.zeros(shape=(3,N))

        for i in range(0, N):
            for j in range(i+1, N):
                r = closest_image_distance(x[:,i],x[:,j],L)
                # calculate force, potential
                Fij, Vij = lennard_jones(r)
                a[:,i] += Fij
                a[:,j] -= Fij
                Vtot += Vij

        v += 0.5*a*dt

        # make sure the particles stay in the box
        for i in range(0, N):
            c = numpy.rint(x[:,i]/L)
            x[:,i] -= c*L
            #calculate kinetic energy
            Ktot += 0.5*numpy.sum(v[:,i]*v[:,i])

        Etot = Vtot + Ktot
        v_sum = numpy.sum(v,1)

        return x,v,a,Vtot,Ktot,Etot,v_sum,dx

    @jit
    def Cv(K_vec, N):
        Kvar = numpy.var(K_vec)
        Kmean2 = (K_vec.mean())**2
        return 3*N*Kmean2/(2*Kmean2-3*N*Kvar)

    @jit 
    def pressure (N, T, x, v, a, rho, r_cut):
        sum1 = 0
        for i in range (0, N) :
            for j in range (1+i, N): 
                    r = closest_image_distance(x[:,i],x[:,j],L)
                    rlen = numpy.sqrt(numpy.sum(r*r))
                    Fmin = -lennard_jones(rlen)[0]
                    sum1 += rlen*Fmin#
        P_comp = 1 - sum1/(3*N*T) + (2*math.pi*rho/(3*T))*(8*r_cut**(-3)-48/9*r_cut**(-9))#this is actually the compressibility factor
        return P_comp

    @jit
    def spacial_corr(x, N, L, bin_size, bin_count):
        bins = numpy.zeros(bin_count)
        for i in range(0,N):
            for j in range(0,N):
                if i == j:
                    continue
                r = closest_image_distance(x[:,i],x[:,j],L)
                r_len = numpy.sqrt(numpy.sum(r*r))
                bins[math.floor(r_len/bin_size)] += 1
        return bins

    #@jit
    def graph(N, L, x, v, a, dt, n_t, n_iter, n_iter_init, bin_count, bin_size, r_all):
        
        bins = numpy.zeros(bin_count)
        Vtot = numpy.zeros(n_iter)
        Ktot = numpy.zeros(n_iter)
        Etot = numpy.zeros(n_iter)
        v_sum = numpy.zeros(n_iter)
        Tcurrent = numpy.zeros(n_iter)
        meandxlen = numpy.zeros(n_iter)
        totdx = numpy.zeros([3,N])
        i = 0
        i_bin = 0
        while i < n_iter:
            if i%n_iter_cut == 0:
                t = time.time()
                r_all = all_distance(x, N, L, rcut, rrms)
                elapsed = time.time() - t
                print("-------------------------------r_all function took",elapsed)
            print("iteration",i)
            t = time.time()
            x, v, a, Vtot[i], Ktot[i], Etot[i], v_sum_vec, dx = update_cut(N, L, x, v, a, dt, n_t, r_all)
            #x, v, a, Vtot[i], Ktot[i], Etot[i], v_sum_vec, dx = update(N, L, x, v, a, dt, n_t)
            elapsed = time.time() - t
            print("update function took",elapsed)
            v_sum[i] = numpy.sqrt(numpy.sum(v_sum_vec*v_sum_vec))/N
            Tcurrent[i] = Ktot[i]*2/(3*N)
            print('Tcurrent[i]= ', Tcurrent[i])
            if i < n_iter_init:
                if i > 10 and i%30 == 0:
                    #thermostat: scale velocity
                    labda = numpy.sqrt((N-1)*(3/2)*T/Ktot[i])
                    v *= labda
            elif Tcurrent[i] > (1.1*T):
                #thermostat: scale velocity
                labda = numpy.sqrt((N-1)*(3/2)*T/Ktot[i])
                v *= labda
                totdx += dx
                totdxlen = numpy.sqrt(numpy.sum(totdx*totdx,0))
                meandxlen[i] = totdxlen.mean()
            elif i%10 == 0:
                #correlation bins
                new_bins = spacial_corr(x,num_particles,L,bin_size,bin_count)
                for j in range(0,bin_count):
                    bins[j] += new_bins[j]
                totdx += dx
                totdxlen = numpy.sqrt(numpy.sum(totdx*totdx,0))
                meandxlen[i] = totdxlen.mean()
                i_bin += 1#amount of times binned to normalize
            else:
                #diffusion length
                totdx += dx
                totdxlen = numpy.sqrt(numpy.sum(totdx*totdx,0))
                meandxlen[i] = totdxlen.mean()
            i += 1
        
        print('i_bin= ',i_bin)
        print('n_iter-n_iter_init= ', n_iter-n_iter_init)
        for j in range(0,bin_count):
            bins[j] *= L*L*L/(N*(N-1))/(4*math.pi*((j+0.5)*bin_size)**2*bin_size)
        bins /= i_bin#divided by amount of times binned

        P_beta = pressure (N, T, x, v, a, rho, rcut)
        CvN = Cv(Ktot[n_iter_init:n_iter],N)/N
        

        return CvN, meandxlen, P_beta, bins, Vtot, Ktot, Etot, Tcurrent, v_sum


    #######################
    # program entry point #
    #######################



    x = initial_positions(num_particles)
    v = initial_velocities(num_particles,T)
    a = initial_accelerations(num_particles)
    
    #r_all = numpy.zeros((num_particles, num_particles))

    t_all = time.time()
    r_all = all_distance(x, num_particles, L, rcut, rrms)
    est = time.time()-t_all
    print('r_all took  ',est, 'seconds')
    #ascat = anim_md.AnimatedScatter(num_particles, L, x, v, a, dt, n_t, update)
    #ascat.show()

    CvN, meandxlen, Pbeta, bins, Vtot, Ktot, Etot, Tcurrent, v_sum = graph(num_particles, L, x, v, a, dt, n_t, n_iter, n_iter_init, bin_count, bin_size, r_all)

    return CvN, Pbeta, bins, Vtot, Ktot, Etot, Tcurrent, meandxlen, v_sum

